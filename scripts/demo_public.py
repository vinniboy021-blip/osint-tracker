"""Small opt-in demonstration against a public, read-only GitHub endpoint.
It does not write to the platform and never treats the response as evidence.
"""
import json, os, urllib.request
url=os.getenv("DEMO_URL","https://api.github.com/repos/psf/requests")
request=urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","User-Agent":"osint-tracker-demo"})
with urllib.request.urlopen(request,timeout=10) as response:
    payload=json.load(response)
print(json.dumps({"test_source":url,"name":payload.get("full_name"),"stars":payload.get("stargazers_count")},ensure_ascii=False))
