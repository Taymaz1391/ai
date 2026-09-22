import argparse
import os
import threading
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from model import ByteTokenizer, load_checkpoint

app=FastAPI(title="Local AI Studio",version="1.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET","POST"],allow_headers=["*"])
model=None; device="cpu"; tokenizer=ByteTokenizer(); sessions={}; lock=threading.Lock()
class ChatRequest(BaseModel):
    message:str=Field(min_length=1,max_length=12000)
    session_id:str="default"
    max_new_tokens:int=Field(default=180,ge=1,le=1024)
    temperature:float=Field(default=.75,gt=0,le=2)
    top_k:int=Field(default=40,ge=0,le=256)
    top_p:float=Field(default=.92,gt=0,le=1)
@app.get("/")
def home(): return FileResponse(os.path.join(os.path.dirname(__file__),"index.html"))
@app.get("/health")
def health(): return {"ok":model is not None,"device":device,"local_only":True,"sessions":len(sessions)}
@app.delete("/sessions/{session_id}")
def clear(session_id:str): sessions.pop(session_id,None); return {"ok":True}
@app.post("/chat")
def chat(req:ChatRequest):
    if model is None: raise HTTPException(503,"checkpoint is not loaded")
    with lock:
        history=sessions.setdefault(req.session_id,[])
        context="\n".join(f"کاربر: {u}\nدستیار: {a}" for u,a in history[-6:])
        prompt=f"{context}\nکاربر: {req.message}\nدستیار:".strip()
        ids=torch.tensor([tokenizer.encode(prompt)],dtype=torch.long,device=device)
        out=model.generate(ids,req.max_new_tokens,req.temperature,req.top_k,req.top_p)
        answer=tokenizer.decode(out[0,ids.shape[1]:].tolist()).strip(); history.append((req.message,answer)); del history[:-12]
        return {"answer":answer,"session_id":req.session_id}
def main():
    global model,device
    p=argparse.ArgumentParser(); p.add_argument("--checkpoint",required=True); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=8000); a=p.parse_args()
    device="cuda" if torch.cuda.is_available() else "cpu"; model=load_checkpoint(a.checkpoint,device)
    import uvicorn; uvicorn.run(app,host=a.host,port=a.port)
if __name__=="__main__": main()
