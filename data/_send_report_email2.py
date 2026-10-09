import json, urllib.request
key = "am_us_inbox_815c96b569d38aa68e9c41bc1a51a5fe16086de96fe26ba8ac6d0fce99100e61"
md = open("C:/Users/schof/veracity2/data/_report_email.md").read()
msg = {
    "to": ["h4martylaptop@agentmail.to"],
    "subject": "Seer Score Daily Report + ETAs",
    "text": md,
    "html": "<pre style=\"font-family:Consolas,monospace;font-size:12px\">" + md.replace("&","&amp;").replace("<","&lt;") + "</pre>",
}
req = urllib.request.Request(
    "https://api.agentmail.to/v0/inboxes/h4martylaptop@agentmail.to/messages/send",
    data=json.dumps(msg).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.status, r.read().decode()[:300])
except urllib.error.HTTPError as e:
    print("ERR", e.code, e.read().decode()[:400])
