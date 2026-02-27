from beartype import beartype
import asyncio
import httpx
import time
from pathlib import Path
import tomllib
from cachetools import LRUCache
from .model import config_
import json
import ipaddress

class HowBoutNo():
    @beartype
    def __init__(self, app, config: str | None = None):
        self.app = app

        if config:
            path = Path(config)
            if not path.exists():
                raise Exception(f"The given config file ({config}) couldn't be found. Make sure it exists in the current working directory.")
            if not path.is_file():
                raise Exception(f"{config} is not a file.")
            try:
                config = tomllib.loads(path.read_text())
            except Exception:
                raise Exception(f"Couldn't parse TOML.")

            self.config = config_.model_validate(config)
        else:
            self.config = None

        if self.config:
            cache_size = self.config.cache.size
            self.cache = LRUCache(maxsize=cache_size)

            if self.config.block_bad_ip.block_inbound_bad_ip:
                print("Fetching inbound IP blacklist data...")
                inbound_bad_ip = httpx.get("https://raw.githubusercontent.com/bitwire-it/ipblocklist/main/inbound.txt", timeout=httpx.Timeout(30.0))
                self.inbound_bad_ip_list = set(inbound_bad_ip.text.splitlines())
            if self.config.block_bad_ip.block_outbound_bad_ip:
                print("Fetching outbound IP blocklist data...")
                outbound_bad_ip = httpx.get("https://raw.githubusercontent.com/bitwire-it/ipblocklist/main/outbound.txt", timeout=httpx.Timeout(30.0))
                self.outbound_bad_ip_list = set(outbound_bad_ip.text.splitlines())
            
        self.reset = 0

    async def __call__(self, scope, receive, send):

        if scope["type"] != "http" or not self.config:
            return await self.app(scope, receive, send)

        async def block_response_logger(obj, type):
            if not self.config.disable_logging.disable_logging:
                print(f"Blocked '{ip}' from accessing '{path}' based on {type} block condition.")
            return await obj(send)
        
        # Normalize IP
        ip = str(ipaddress.ip_address(scope["client"][0]))
        path = scope.get("path")


        if ip in self.config.block_ip:
            all_block_response = self.config.response.all.get_response_obj() if self.config.response.all else self.config.response.ip.get_response_obj()
            return await all_block_response(send)

        if ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_reserved:
            await send({
                'type': 'http.response.start',
                'status': 503,
                'headers': [
                    [b'content-type', b'application/json'],
                ],
            })
            await send({
                'type': 'http.response.body',
                'body': json.dumps({"detail": "Service Unavailable"}).encode(),
            })
            return
        
        cache_config_invalidate_success_after = self.config.cache.invalidate_success_after
        cache_config_invalidate_error_after = self.config.cache.invalidate_error_after

        cache_entry = self.cache.get(ip)
        in_cache = bool(cache_entry)

        if in_cache:
            """
            We are classifying cache entries as successful if the status code of the response is 200,
            and unsuccessful otherwise. The response body from ip-api.com has a 'status' field which
            can have two values: 'success' and 'fail'. We are excluding the 'status' field in the response 
            body from this classification. We can't solely rely on the 'status' field in the
            response body for this classification, because we need a way to classify entries that are in
            the cache but the request to ip-api.com failed for them, for example due to a network error,
            in such cases, there won't be a response body from ip-api.com and therefore we won't have the
            'status' field in the response body to rely on for the classification. We could also consider a
            hybrid approach of relying on both the status code of the response and the 'status' field
            in the response body for the classification. Let's see what happens if this approach is used.
            The 'status' field in the response body from ip-api.com is 'success' when the IP lookup was
            successful and the IP is not within a reserved or private range, if this is the case, the
            status code will be 200 and the entry will be classified as successful, which is what we want.
            It is 'fail' only when the IP is within a reserved or private range or it's an invalid IP
            however in such cases, the status code is still 200, meaning the request to ip-api.com was
            successful, but the lookup was not successful because the IP is within a reserved or private
            range or it's an invalid IP. The failure is not temporary and most likely will not be resolved
            by retrying after some time because they aren't a failure of the service but a characteristic
            of the IP address being looked up, which justifies classifying such entries as successful
            Therefore, we want to cache them to avoid making unnecessary requests to ip-api.com for
            reserved, private and invalid IPs.Therefore, we should not include the 'status' field in the
            classification and only rely on the status code of the response.
            """
            is_successful_cache = cache_entry["data"]["status_code"] == 200
            success_cache_invalidate_time = cache_entry["last_updated"] + cache_config_invalidate_success_after
            error_cache_invalidate_time = cache_entry["last_updated"] + cache_config_invalidate_error_after

        if not in_cache or (is_successful_cache and time.time() >= success_cache_invalidate_time and cache_config_invalidate_success_after != 0) or (not is_successful_cache and time.time() >= error_cache_invalidate_time and cache_config_invalidate_error_after != 0):
            rate_limited = False if time.time() >= self.reset else True

            if rate_limited:
                await send({
                    'type': 'http.response.start',
                    'status': 503,
                    'headers': [
                        [b'content-type', b'application/json'],
                        [b'Retry-After', str(self.reset).encode()]
                    ],
                })
                await send({
                    'type': 'http.response.body',
                    'body': json.dumps({"detail": "Service Unavailable"}).encode(),
                })
                return
        
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://ip-api.com/json/{ip}?fields=status,continentCode,countryCode,as,reverse,proxy,hosting")

            if response.status_code != 200:
                self.cache[ip] = {
                    "data": {
                        "status_code": response.status_code,
                        "response": response.json() if response.content else None

                    },
                    "last_updated": time.time()
                }

                await send({
                    'type': 'http.response.start',
                    'status': 503,
                    'headers': [
                        [b'content-type', b'application/json'],
                    ],
                })
                await send({
                    'type': 'http.response.body',
                    'body': json.dumps({"detail": "Service Unavailable"}).encode(),
                })
                return

            if response.headers["X-Rl"] == "0":
                rate_limited = True
                self.reset = time.time() + response.headers["X-Ttl"]

            response_json = response.json()

            if response_json["status"] != "success":
                await send({
                    'type': 'http.response.start',
                    'status': 503,
                    'headers': [
                        [b'content-type', b'application/json'],
                    ],
                })
                await send({
                    'type': 'http.response.body',
                    'body': json.dumps({"detail": "Service Unavailable"}).encode(),
                })
                return
            
            self.cache[ip] = {
                "data": {
                    "status_code": response.status_code,
                    "response": response.json() if response.content else None

                },
                "last_updated": time.time()
            }

            continent = response_json["continentCode"]
            country = response_json["countryCode"]
            asn = int(response_json["as"].split(" ")[0][2:]) if response_json["as"] else response_json["as"]
            rdns_hostname = response_json["reverse"]
            is_hosting = response_json["hosting"]
            is_proxy = response_json["proxy"]

            if self.config.response.all:
                all_block_response = self.config.response.all.get_response_obj()

                if self.config.block_bad_ip.block_inbound_bad_ip and ip in self.inbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "inbound bad IP")
                if self.config.block_bad_ip.block_outbound_bad_ip and ip in self.outbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "outbound bad IP")
                if continent in self.config.block_continent.block_continent and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "continent")
                if country in self.config.block_country.block_country and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "country")
                if asn in self.config.block_asn.block_asn and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "ASN")
                if rdns_hostname in self.config.block_rdns_hostname.block_rdns_hostname and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "RDNS hostname")
                if not self.config.allow_hosting.allow_hosting and is_hosting and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "hosting")
                if not self.config.allow_proxy.allow_proxy and is_proxy and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                    return await block_response_logger(all_block_response, "proxy")

                return await self.app(scope, receive, send)

            continent_response = self.config.response.continent.get_response_obj()
            country_response = self.config.response.country.get_response_obj()
            asn_response = self.config.response.asn.get_response_obj()
            rdns_hostname_response = self.config.response.rdns_hostname.get_response_obj()
            hosting_response = self.config.response.hosting.get_response_obj()
            proxy_response = self.config.response.proxy.get_response_obj()

            if self.config.block_bad_ip.block_inbound_bad_ip and ip in self.inbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(self.config.response.bad_ip.get_response_obj(), "inbound bad IP")
            if self.config.block_bad_ip.block_outbound_bad_ip and ip in self.outbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(self.config.response.bad_ip.get_response_obj(), "outbound bad IP")
            if continent in self.config.block_continent.block_continent and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(continent_response, "continent")
            if country in self.config.block_country.block_country and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(country_response, "country")
            if asn in self.config.block_asn.block_asn and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(asn_response, "ASN")
            if rdns_hostname in self.config.block_rdns_hostname.block_rdns_hostname and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(rdns_hostname_response, "RDNS hostname")
            if not self.config.allow_hosting.allow_hosting and is_hosting and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(hosting_response, "hosting")
            if not self.config.allow_proxy.allow_proxy and is_proxy and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(proxy_response, "proxy")

            return await self.app(scope, receive, send)


        cache = self.cache[ip]

        continent = cache["data"]["response"]["continentCode"]
        country = cache["data"]["response"]["countryCode"]
        asn = int(cache["data"]["response"]["as"].split(" ")[0][2:]) if cache["data"]["response"]["as"] else None
        rdns_hostname = cache["data"]["response"]["reverse"]
        is_hosting = cache["data"]["response"]["hosting"]
        is_proxy = cache["data"]["response"]["proxy"]

        if cache["data"]["status_code"] != 200 or cache["data"]["response"]["status"] != "success":
            await send({
                'type': 'http.response.start',
                'status': 503,
                'headers': [
                    [b'content-type', b'application/json'],
                ],
            })
            await send({
                'type': 'http.response.body',
                'body': json.dumps({"detail": "Service Unavailable"}).encode(),
            })
            return

        if self.config.response.all:
            all_block_response = self.config.response.all.get_response_obj()

            if self.config.block_bad_ip.block_inbound_bad_ip and ip in self.inbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "inbound bad IP")
            if self.config.block_bad_ip.block_outbound_bad_ip and ip in self.outbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "outbound bad IP")
            if continent in self.config.block_continent.block_continent and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "continent")
            if country in self.config.block_country.block_country and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "country")
            if asn in self.config.block_asn.block_asn and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "ASN")
            if rdns_hostname in self.config.block_rdns_hostname.block_rdns_hostname and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "RDNS hostname")
            if not self.config.allow_hosting.allow_hosting and is_hosting and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "hosting")
            if not self.config.allow_proxy.allow_proxy and is_proxy and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
                return await block_response_logger(all_block_response, "proxy")

            return await self.app(scope, receive, send)

        continent_response = self.config.response.continent.get_response_obj()
        country_response = self.config.response.country.get_response_obj()
        asn_response = self.config.response.asn.get_response_obj()
        rdns_hostname_response = self.config.response.rdns_hostname.get_response_obj()
        hosting_response = self.config.response.hosting.get_response_obj()
        proxy_response = self.config.response.proxy.get_response_obj()

        if self.config.block_bad_ip.block_inbound_bad_ip and ip in self.inbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(self.config.response.bad_ip.get_response_obj(), "inbound bad IP")
        if self.config.block_bad_ip.block_outbound_bad_ip and ip in self.outbound_bad_ip_list and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(self.config.response.bad_ip.get_response_obj(), "outbound bad IP")
        if continent in self.config.block_continent.block_continent and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(continent_response, "continent")
        if country in self.config.block_country.block_country and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(country_response, "country")
        if asn in self.config.block_asn.block_asn and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(asn_response, "ASN")
        if rdns_hostname in self.config.block_rdns_hostname.block_rdns_hostname and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(rdns_hostname_response, "RDNS hostname")
        if not self.config.allow_hosting.allow_hosting and is_hosting and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(hosting_response, "hosting")
        if not self.config.allow_proxy.allow_proxy and is_proxy and ip not in self.config.exception_ip.exception_ip and path not in self.config.exception_path:
            return await block_response_logger(proxy_response, "proxy")

        return await self.app(scope, receive, send)
