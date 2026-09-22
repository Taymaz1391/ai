import argparse, json, os, sys, torch
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from model import ByteTokenizer, load_checkpoint

app=FastAPI(title='Local AI Studio', version='1.0.0'); app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
model=None; device='cpu'; tokenizer=ByteTokenizer(); sessions={}
@app.get('/')
def home(): return FileResponse(os.path.join(os.path.dirname(__file__),'index.html'))
@app.get('/health')
def health(): return {'ok': model is not None, 'device': device, 'local_only': True}
@app.post('/chat')
async def chat(req: Request):
    if model is None: return JSONResponse({'error':'checkpoint is not loaded'},status_code=503)
    body=await req.json(); text=str(body.get('message','')).strip(); sid=str(body.get('session_id','default'))
    if not text: return JSONResponse({'error':'message is empty'},status_code=400)
    history=sessions.setdefault(sid,[]); prompt='\n'.join(f'کاربر: {x[0]}\nدستیار: {x[1]}' for x in history[-6:])+f'\nکاربر: {text}\nدستیار:'
    ids=torch.tensor([tokenizer.encode(prompt)],dtype=torch.long,device=device); out=model.generate(ids,int(body.get('max_new_tokens',180)),float(body.get('temperature',.75)),int(body.get('top_k',40)),float(body.get('top_p',.92))); answer=tokenizer.decode(out[0].tolist()[len(ids[0]):]).strip(); history.append((text,answer)); return {'answer':answer,'session_id':sid}

def main():
    global model,device
    p=argparse.ArgumentParser(); p.add_argument('--checkpoint',required=True); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8000); a=p.parse_args(); device='cuda' if torch.cuda.is_available() else 'cpu'; model=load_checkpoint(a.checkpoint,device); import uvicorn; uvicorn.run(app,host=a.host,port=a.port)
if __name__=='__main__': main()
