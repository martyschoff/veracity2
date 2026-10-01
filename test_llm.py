import json, urllib.request

def llm(messages, timeout=120):
    req=urllib.request.Request('http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions',
        data=json.dumps({'model':'qwen3-coder:30b-32k','messages':messages,'stream':False}).encode(),
        headers={'Content-Type':'application/json'})
    r=json.load(urllib.request.urlopen(req, timeout=timeout))
    return r['choices'][0]['message']['content']

out=llm([{'role':'user','content':'Reply with exactly: OK'}])
print(repr(out))
