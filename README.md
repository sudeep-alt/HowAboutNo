# HowAboutNo
*Say no to unwanted traffic*

**HowAboutNo** is an open source ASGI middleware designed to block unwanted traffic on web apps. Supports all ASGI frameworks.

**Version:** `0.1.0`

## Features
- Block traffic based on IP, continent, country, ASN, RDNS hostname, hosting and proxy status.
- Customizable responses for blocked traffic.
- Easy integration with any ASGI framework.
- Simple configuration using a TOML file.
- Lightweight and efficient implementation.
- Reliable IP lookups using [ip-api.com](http://ip-api.com/).
- Caching of IP lookup results to minimize latency and avoid hitting rate limits.
- Configurable cache invalidation times for successful and unsuccessful entries.
- Exception lists to allow certain IPs and paths to bypass blocking rules.
- Optional logging of blocked requests.

## Installation
```bash
pip install howaboutno
```
or whatever method you prefer to install Python packages.

## Usage
1. Create a configuration file (e.g., `config.toml`) either manually or by runnning the `howaboutno` command, which generates a sample config file in the current working directory.
2. Wrap your ASGI app with the `HowAboutNo` middleware, passing the path to your configuration file.

That's it. HowAboutNo will now block unwanted traffic based on the rules defined in your configuration file.

### Configuration
The configuration file is in TOML format and supports the following options:
- `block_ip`: List of IP addresses to block.
- `block_continent`: List of continent codes to block.
- `block_country`: List of country codes to block.
- `block_asn`: List of ASNs to block.
- `block_rdns_hostname`: List of RDNS hostnames to block.
- `allow_hosting`: Whether to block hosting providers.
- `allow_proxy`: Whether to block proxies.
- `exception_ip`: List of IP addresses to exclude from blocking.
- `exception_path`: List of URL paths to exclude from blocking.
- `response`: Custom responses for different block types.
- `cache`: Cache settings, including size and invalidation times.
- `disable_logging`: Option to disable logging of blocked requests.


### Detailed config example
```toml
# Block IPs (both IPv4 and IPv6 supported)
[block_ip]
block_ip = ["1.1.1.1", "2.2.2.2"]

# Block bad IPs from public blocklists (fetched at app startup)
[block_bad_ip]
block_inbound_bad_ip = true
block_outbound_bad_ip = true

# Block continents (2-letter continent codes)
[block_continent]
block_continent = ["AS", "EU"]

# Block countries (ISO 3166-1 alpha-2 country codes)
[block_country]
block_country = ["IN", "CN"]

# Block ASNs (Autonomous System Numbers)
[block_asn]
block_asn = [12345, 67890]

# Block reverse DNS hostnames
[block_rdns_hostname]
block_rdns_hostname = ["badhost.example.com", "malicious.example.net"]

# Allow hosting providers (true/false)
[allow_hosting]
allow_hosting = false

# Allow proxies (true/false)
[allow_proxy]
allow_proxy = false

# Exception IPs (list of IP addresses to exclude from blocking)
[exception_ip]
exception_ip = ["3.3.3.3"]

# Exception paths (list of URL paths to exclude from blocking)
[exception_path]
exception_path = ["/health", "/status"]

# Custom responses for different block types

# Response for IP blocks
[response.ip]
# The response string can be a JSON string, HTML string, or plain text string based on the specified return type.
response = "{\"detail\": \"Access denied due to your IP address.\"}"
# The status code to return when a block is triggered.
status_code = 403
# The return_as field specifies the format of the response. The supported values are "JSON", "HTML", and "TEXT". Case-insensitive.
return_as = "JSON"

# Similarly, you can define custom responses for continent, country, ASN, rdns_hostname, hosting, and proxy blocks.

# Response for all blocks (overrides specific block responses if defined)
[response.all]
response = "<h1>Access Denied</h1><p>Your request has been blocked.</p>"
status_code = 403
return_as = "HTML"

# Cache settings

[cache]
# Maximum number of entries in the cache
size = 512
# Time in seconds after which a successful cache entry should be invalidated (default: 7 days)
invalidate_success_after = 604800
# Time in seconds after which an error cache entry should be invalidated (default: 1 hour)
invalidate_error_after = 3600

# Disable logging (true/false)
[disable_logging]
disable_logging = false
```

## Implementation
### FastAPI
```python
from fastapi import FastAPI
from howaboutno import HowAboutNo

app = FastAPI()

@app.get("/")
def root():
    return {
        "message": "Hello, world!"
    }

# Must be at the very end after all routes have been defined and after all other middleware have been added if there are any.
app = HowAboutNo(app, config="config.toml")
```

> [!NOTE]
Wrapping the app with HowAboutNo at the end instead of using `add_middleware` is recommended since Starlette, which FastAPI is built on top of, suppresses exceptions raised in middleware's initialization when using `add_middleware`, and only raised when a request is made, which can make debugging difficult. Wrapping the app with HowAboutNo directly will ensure that HowAboutNo is the outermost layer of the app and any exceptions raised in its initialization will be raised immediately, making them easier to debug.

### Starlette
```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route
from howaboutno import HowAboutNo

async def root(request: Request):
    return JSONResponse({"message": "Hello, world!"})

routes = [
    Route("/", root)
]

app = Starlette(routes=routes)

# Must be at the very end after all routes have been defined and after all other middleware have been added if there are any.
app = HowAboutNo(app, config="config.toml")
```

> [!NOTE]
Similarly to FastAPI, wrapping the app with HowAboutNo at the end instead of using Starlette's `Middleware` class is recommended to ensure that any exceptions raised in the initialization of HowAboutNo are raised immediately, making them easier to debug.

### Pure ASGI
```python
from howaboutno import HowAboutNo

async def app(scope, receive, send):
    if scope["type"] == "http":
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
            ],
        })

        await send({
            "type": "http.response.body",
            "body": b"Hello, world!",
        })

# Must be at the very end after all routes have been defined and after all other middleware have been added if there are any.
app = HowAboutNo(app, config="config.toml")


### Other ASGI frameworks
HowAboutNo can be used with any ASGI framework by wrapping the ASGI app with HowAboutNo and passing the path to the configuration file after all routes and other middleware have been defined.

## Architecture
### IP retrieval
The client IP is retrieved from `scope["client"][0]`, the middleware assumes the client key always exists. Additionally, it assumes `scope["client"][0]` is a valid IP address.

### Request blocking
A request is blocked if **any** of the following match (checked top → bottom):

- IP is in `block_ip` and absent from `exception_ip` and path is absent from `exception_path`
- `block_inbound_bad_ip` is true and IP is in the inbound bad IP blocklist and IP is absent from `exception_ip` and path is absent from `exception_path`
- `block_outbound_bad_ip` is true and IP is in the outbound bad IP blocklist and IP is absent from `exception_ip` and path is absent from `exception_path`
- Continent is in `block_continent` and absent from `exception_ip` and path is absent from `exception_path`
- Country is in `block_country` and absent from `exception_ip` and path is absent from `exception_path`
- ASN is in `block_asn` and absent from `exception_ip` and path is absent from `exception_path`
- rDNS hostname is in `block_rdns_hostname` and absent from `exception_ip` and path is absent from `exception_path`
- Hosting IP while `allow_hosting = false` and IP is absent from `exception_ip` and path is absent from `exception_path`
- Proxy IP while `allow_proxy = false` and IP is absent from `exception_ip` and path is absent from `exception_path`

**Rule**
- Only the response for the *first matching block condition* is returned.

**Example**
- If an IP matches both `block_country` and `block_asn`
- The `block_country` response is used

### Data source
HowAboutNo uses [ip-api.com](http://ip-api.com/) for IP lookups, which provides data on continent, country, ASN, rDNS hostname, hosting and proxy status for a given IP address.
> [!NOTE]
The data returned by ip-api.com may contain errors or be inaccurate. HowAboutNo does not make any guarantees regarding the accuracy of the data returned by ip-api.com and is not responsible for any consequences that may arise from blocking decisions based on this data.
The middleware returns a 503 if it fails to lookup the data of the IP address.

HowAboutNo also inherits the limitations of ip-api.com, including potential inaccuracies in the data and rate limits on requests. Enabling caching can help mitigate the impact of rate limits, but it's important to be aware of these limitations when using HowAboutNo.

> [!WARNING]
HowAboutNo relies on ip-api.com for its blocking functionality, and ip-api.com has its own terms of service which must be followed. Make sure to review ip-api.com's terms of service before using HowAboutNo, especially if you plan to use it for commercial purposes.

### Caching
HowAboutNo uses an LRU cache to store IP lookup results from ip-api.com.

To disable caching, set `size` to `0`.  
To disable cache invalidation, set `invalidate_success_after` or `invalidate_error_after` to `0` according to your needs.

- **When caching and invalidation are enabled:**
  - On the first request from an IP address, its data is looked up and cached (with eviction if the cache is full).
  - On subsequent requests from the same IP:
    - If the cache entry is successful (status code 200) and time elapsed since caching exceeds `invalidate_success_after`, or if the cache entry is an error (non-200 status code) and time elapsed since caching exceeds `invalidate_error_after`, the IP is looked up again and the cache entry is refreshed.
    - Otherwise, the cached data is returned.

- **When caching is enabled but invalidation is disabled:**
  - On the first request from an IP address, its data is looked up and cached, evicting older entries if necessary.
  - On subsequent requests from the same IP, the cached data is returned indefinitely until it is evicted due to cache size limits.
  - This applies individually to successful and error entries based on the `invalidate_success_after` and `invalidate_error_after` settings.

- **When caching is disabled:**
  - The IP address is looked up on every request.

## FAQ
### General
- **Q: Will this middleware work with any ASGI framework?**
    - A: Yes, HowAboutNo is built to be compatible with any ASGI framework. You can wrap any ASGI app with HowAboutNo to add the blocking functionality.
- **Q: Why can't I use Cloudflare or a similar service instead of this middleware?**
    - A: To avoid corporate dependencies and have full control over the blocking logic and responses. HowAboutNo allows you to define custom blocking rules and responses without relying on third-party services, which can be important for privacy, security, and customization reasons.
- **Q: Is HowAboutNo free to use?**
    - A: Yes, HowAboutNo is open source and free to use under the MIT License.
- **Q: Why ASGI middleware and not WSGI middleware?**
    - A: To be honest, I don't have a specific reason for choosing ASGI over WSGI. I chose ASGI simply because it's the modern standard for Python web applications.
- **Q: Can I use HowAboutNo with a WSGI app?**
    - A: Not directly, since HowAboutNo is designed as ASGI middleware. However, you can use an ASGI-to-WSGI adapter like `asgiref.wsgi.WsgiToAsgi` to wrap your WSGI app and then apply HowAboutNo as ASGI middleware to the wrapped app.
- **Q: Can I use this for commercial purposes?**
    - A: Yes, but also no, you can use the source code for commercial purposes. However, the IP lookup functionality relies on [ip-api.com](http://ip-api.com/), which has its own terms of service which does not allow commercial use without a paid plan.
- **Q: Why such a casual name for a middleware?**
    - A: Because I said so!
- **Q: Will I get a girlfriend by using this middleware?**
    - A: Uh, maybe? Who knows!

### Architecture
- **Q: Will my app be affected by [ip-api.com](https://ip-api.com/) rate limits?**
    - A: Yes, but not in the way you might think. Caching is implemented to minimize the number of requests made to ip-api.com, which helps avoid hitting rate limits. However, if you do hit a rate limit, HowAboutNo will return a 503 Service Unavailable response for requests that require an IP lookup until the rate limit resets. This means that your app will not be able to perform IP lookups during this time, but it will still be able to serve requests that do not require IP lookups (e.g., requests from IPs that are already in the cache).
- **Q: What happens if ip-api.com is unreachable or returns an error?**
    - A: If ip-api.com returns an error or is unreachable, HowAboutNo will treat the lookup as unsuccessful and will return a 503 Service Unavailable response.
- **Q: If multiple block conditions match for a request, which response is returned?**
    - A: Only the response for the first matching block condition is returned. The block conditions are checked in the following order: IP, continent, country, ASN, rDNS hostname, hosting status, and proxy status. So if a request matches both `block_country` and `block_asn`, the response defined for `block_country` will be returned.
- **Q: Can I exclude certain IPs or paths from being blocked?**
    - A: Yes, you can use the `exception_ip` and `exception_path` settings in the configuration file to specify IP addresses and URL paths that should be excluded from blocking rules. If a request matches a block condition but the IP is in `exception_ip` or the path is in `exception_path`, the request will not be blocked based on that condition. 
- **Q: What happens if an IP address matches a block condition but is also in the exception list?**
    - A: If an IP address matches a block condition but is also listed in `exception_ip`, the blocking rules will be bypassed for that IP address, and the request will not be blocked based on that condition. The same applies to URL paths listed in `exception_path`. This allows you to have granular control over which IPs and paths are subject to blocking rules.
- **Q: What happens if an IP address is present in both `block_ip` and `exception_ip`?**
    - A: If an IP address is present in both `block_ip` and `exception_ip`, the blocking rules will be bypassed for that IP address, and the request will not be blocked based on the `block_ip` condition. The presence of the IP address in `exception_ip` takes precedence over its presence in `block_ip`.
- **Q: If caching is enabled and an IP address is blocked based on a cached entry, but the actual data for that IP has changed since it was cached, will the middleware still block the request?**
    - A: Yes, if the cache entry for that IP address indicates that it should be blocked, the middleware will block the request based on the cached data. The cache invalidation settings determine how long entries remain in the cache before they are refreshed, but while they are in the cache, their data is used for blocking decisions.
- **Q: What do `invalidate_success_after` and `invalidate_error_after` do?**
    - A: `invalidate_success_after` specifies the time in seconds after which a successful cache entry (status code 200) should be invalidated and refreshed on the next request. `invalidate_error_after` specifies the time in seconds after which an unsuccessful cache entry (non-200 status code) should be invalidated and refreshed on the next request. Setting either of these to `0` disables invalidation for that type of entry, meaning entries will remain in the cache indefinitely until evicted due to cache size limits.

### Troubleshooting
- **Q: I'm seeing a lot of 503 Service Unavailable responses. What could be causing this?**
    - A: This could be caused by several factors:
        - You might be hitting the rate limits of ip-api.com, especially if caching is disabled or if you have a high volume of requests from unique IP addresses. In this case, you would need to wait until the rate limit resets.
        - ip-api.com might be experiencing downtime or issues, which would cause lookups to fail and result in 503 responses. You can check the status of ip-api.com to see if there are any reported issues.
        - There could be a network issue preventing your server from reaching ip-api.com, which would also lead to failed lookups and 503 responses. You can check your server's network connectivity to ensure it can reach ip-api.com.

- **Q: My configuration changes are not taking effect. What should I do?**
    - A: The configuration file is read when the HowAboutNo middleware is initialized. If you make changes to the configuration file after the middleware has been initialized, those changes will not take effect until the middleware is reloaded. To apply configuration changes, you will need to restart your ASGI application so that the HowAboutNo middleware can read the updated configuration file.

Anything else? Please let me know by opening an issue!

## LICENSE
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements
- [ip-api.com](https://ip-api.com/) for providing the IP data.
- [bitwire-it](https://github.com/bitwire-it) for the [IP blocklist](https://github.com/bitwire-it/ipblocklist/) data.

If you found this project useful, please consider giving it a star!