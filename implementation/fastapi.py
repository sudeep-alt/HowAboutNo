from fastapi import FastAPI
from howaboutno import HowAboutNo

app = FastAPI()

@app.get("/")
def root():
    return {
        "message": "Hello, world!"
    }