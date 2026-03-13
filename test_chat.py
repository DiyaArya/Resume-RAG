import urllib.request, json, sys

try:
    req = urllib.request.Request('http://localhost:8000/api/chat', data=json.dumps({'message': 'how will it affect india'}).encode('utf-8'), headers={'Content-Type': 'application/json'})
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print(e)
    if hasattr(e, 'read'):
        print(e.read().decode())
