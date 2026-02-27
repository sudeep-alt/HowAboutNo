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