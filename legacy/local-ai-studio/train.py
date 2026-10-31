import argparse, math, os, torch
from model import GPTConfig, LocalGPT, ByteTokenizer, save_checkpoint

def batch(data, size, block, device):
    starts=torch.randint(0,len(data)-block-1,(size,)); return (torch.stack([data[i:i+block] for i in starts]).to(device),torch.stack([data[i+1:i+block+1] for i in starts]).to(device))
def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',required=True); p.add_argument('--output',default='checkpoints/local_model.pt'); p.add_argument('--steps',type=int,default=3000); p.add_argument('--batch-size',type=int,default=16); p.add_argument('--block-size',type=int,default=256); p.add_argument('--layers',type=int,default=6); p.add_argument('--heads',type=int,default=6); p.add_argument('--embed',type=int,default=384); p.add_argument('--lr',type=float,default=3e-4); a=p.parse_args()
    text=open(a.input,encoding='utf-8').read(); data=torch.tensor(ByteTokenizer().encode(text),dtype=torch.long)
    if len(data)<=a.block_size+1: raise ValueError('data must be longer than block-size')
    device='cuda' if torch.cuda.is_available() else 'cpu'; cfg=GPTConfig(block_size=a.block_size,n_layer=a.layers,n_head=a.heads,n_embd=a.embed); m=LocalGPT(cfg).to(device); opt=torch.optim.AdamW(m.parameters(),lr=a.lr,weight_decay=.1); os.makedirs(os.path.dirname(a.output) or '.',exist_ok=True)
    m.train()
    for step in range(1,a.steps+1):
        x,y=batch(data,a.batch_size,a.block_size,device); _,loss=m(x,y); opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(m.parameters(),1.0); opt.step()
        if step%50==0 or step==a.steps: print(f'step {step}/{a.steps} loss={loss.item():.4f}')
    save_checkpoint(m,a.output); print('saved',a.output)
if __name__=='__main__': main()
