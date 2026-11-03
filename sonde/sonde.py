import requests, os
os.makedirs("sonde/out",exist_ok=True)
U={"l1":"https://elevenlabsusercontent.com/database/workspace/d0938ae23dd24dbdbb8a3ce1540d3773/content_generation/g1VUQS2mhoYm4ndcjoRb/GSsCz1pirztsRX6x0mSf/content.mp3?Expires=1793732400&KeyName=assets-cdn-key-1&Signature=MQShxoBPMKa39EqhU6D5qqtA8Lg=",
"l2":"https://elevenlabsusercontent.com/database/workspace/d0938ae23dd24dbdbb8a3ce1540d3773/content_generation/64W1zXGvxU5xHIZdVDfb/QwpBo4g3MNuRyWnKyrVL/content.mp3?Expires=1793732400&KeyName=assets-cdn-key-1&Signature=NcTj7NUds6Pwe4lRauBEyzSc3po=",
"l3":"https://elevenlabsusercontent.com/database/workspace/d0938ae23dd24dbdbb8a3ce1540d3773/content_generation/HhOcK1wfK6kElnSZHEse/fXoCRlIzyKIqCUeFHSJp/content.mp3?Expires=1793732400&KeyName=assets-cdn-key-1&Signature=rIzWg5W7ESuTo-LoV0KnpmGuj2A=",
"l4":"https://elevenlabsusercontent.com/database/workspace/d0938ae23dd24dbdbb8a3ce1540d3773/content_generation/6zzHBmzWsXAExAAJFAdA/bFd3bFagDBDUnsNF7Ri0/content.mp3?Expires=1793732400&KeyName=assets-cdn-key-1&Signature=fusjS5-4rslr5V1z1tas2ZbhtGs="}
for k,u in U.items():
    r=requests.get(u,timeout=60); print(k,r.status_code,len(r.content)); open(f"sonde/out/{k}.mp3","wb").write(r.content)
