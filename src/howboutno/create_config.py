def create_config():
    config_content = """
# Block IPs (both IPv4 and IPv6 supported)
[block_ip]
block_ip = ["1.1.1.1", "2.2.2.2"]

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
# The return_as field specifies the format of the response. It can be "JSON", "HTML", or "TEXT".
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
"""
    with open("config.toml", "w") as f:
        f.write(config_content)

