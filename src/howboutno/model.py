from pydantic import BaseModel, field_validator, model_validator, IPvAnyAddress
import json
from http import HTTPStatus
from typing import Any
import ipaddress

class response_model_(BaseModel):
    response: str
    status_code: HTTPStatus
    return_as: str

    @model_validator(mode="after")
    def validate_return_type(self):
        """
        Normalize 'return_as' and verify that it is a supported return format.
        """
        self.return_as = self.return_as.strip().upper()

        if self.return_as not in ["JSON", "HTML", "TEXT"]:
            raise ValueError("\"return_as\" must be either JSON, HTML or TEXT.")

        return self
    
    def get_response_obj(self):
        """
        Convert the response string into a callable ASGI response object based on the specified return type.
        """

        class JSON():
            def __init__(self, content, status_code):
                self.content = content
                self.status_code = status_code
            
            async def __call__(self, send):
                await send({
                    'type': 'http.response.start',
                    'status': self.status_code,
                    'headers': [
                        [b'content-type', b'application/json'],
                    ],
                })          
                await send({
                    'type': 'http.response.body',
                    'body': json.dumps(self.content).encode(),
                })
                return
            
        class HTML():
            def __init__(self, content, status_code):
                self.content = content
                self.status_code = status_code
            
            async def __call__(self, send):
                await send({
                    'type': 'http.response.start',
                    'status': self.status_code,
                    'headers': [
                        [b'content-type', b'text/html'],
                    ],
                })              
                await send({
                    'type': 'http.response.body',
                    'body': self.content.encode(),
                })
                return

        class TEXT():
            def __init__(self, content, status_code):
                self.content = content
                self.status_code = status_code
            
            async def __call__(self, send):
                await send({
                    'type': 'http.response.start',
                    'status': self.status_code,
                    'headers': [
                        [b'content-type', b'text/plain'],
                    ],
                })
                await send({
                    'type': 'http.response.body',
                    'body': self.content.encode(),
                })
                return
            
        if self.return_as == "JSON":
            data = json.loads(self.response)
            response_obj = JSON(content=data, status_code=self.status_code)
            return response_obj
        elif self.return_as == "HTML":
            response_obj = HTML(content=self.response, status_code=self.status_code)
            return response_obj
        elif self.return_as == "TEXT":
            response_obj = TEXT(content=self.response, status_code=self.status_code)
            return response_obj

class block_ip_(BaseModel):
    block_ip: list[IPvAnyAddress] = []

    @field_validator("block_ip", mode="before")
    @classmethod
    def validate_ip_addresses(cls, value):
        return [str(ipaddress.ip_address(ip.strip())) for ip in value]

class block_continent_(BaseModel):
    block_continent: list[str] = []

    @field_validator("block_continent", mode="before")
    @classmethod
    def normalize_continent_codes(cls, value):
        return [code.strip().upper() for code in value]
    
class block_country_(BaseModel):
    block_country: list[str] = []

    @field_validator("block_country", mode="before")
    @classmethod
    def normalize_country_codes(cls, value):
        return [code.strip().upper() for code in value]
    
class block_asn_(BaseModel):
    block_asn: list[int] = []

class block_rdns_hostname_(BaseModel):
    block_rdns_hostname: list[str] = []

    @field_validator("block_rdns_hostname", mode="before")
    @classmethod
    def normalize_hostnames(cls, value):
        return [hostname.strip().lower() for hostname in value]

class block_bad_ip_(BaseModel):
    block_inbound_bad_ip: bool = False
    block_outbound_bad_ip: bool = False

class allow_hosting_(BaseModel):
    allow_hosting: bool = True

class allow_proxy_(BaseModel):
    allow_proxy: bool = True
    
class response_(BaseModel):
    all: response_model_ = None
    ip: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )
    continent: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )
    country: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )
    asn: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )
    rdns_hostname: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )

    bad_ip: response_model_ = response_model_.model_validate(
        {
            "response": "{\"detail\": \"Forbidden\"}",
            "status_code": 403,
            "return_as": "JSON"
        }
    )
    
    hosting: response_model_ = response_model_(response="{\"detail\": \"Forbidden\"}", status_code=403, return_as="JSON")
    proxy: response_model_ = response_model_(response="{\"detail\": \"Forbidden\"}", status_code=403, return_as="JSON")

class exception_path_(BaseModel):
    exception_path: list[str] = []

    @field_validator("exception_path", mode="before")
    @classmethod
    def normalize_exception_paths(cls, value):
        return [path.strip() for path in value]
    
class cache_(BaseModel):
    size: int = 512
    invalidate_success_after: int = 604800 # 7 days
    invalidate_error_after: int = 3600 # 1 hour

class exception_ip_(BaseModel):
    exception_ip: list = []

    @field_validator("exception_ip", mode="before")
    @classmethod
    def validate_exception_ip_addresses(cls, value):
        return [str(ipaddress.ip_address(ip.strip())) for ip in value]
    
class disable_logging_(BaseModel):
    disable_logging: bool = False
    

class config_(BaseModel):
    block_ip: block_ip_ = block_ip_()
    block_bad_ip: block_bad_ip_ = block_bad_ip_()
    block_continent: block_continent_ = block_continent_()
    block_country: block_country_ = block_country_()
    block_asn: block_asn_ = block_asn_()
    block_rdns_hostname: block_rdns_hostname_ = block_rdns_hostname_()
    allow_hosting: allow_hosting_ = allow_hosting_()
    allow_proxy: allow_proxy_ = allow_proxy_()
    exception_ip: exception_ip_ = exception_ip_()
    exception_path: exception_path_ = exception_path_()
    response: response_ = response_()
    cache: cache_ = cache_()
    disable_logging: disable_logging_ = disable_logging_()