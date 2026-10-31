"""Local decoder-only GPT. No network calls are made by this module."""
from dataclasses import asdict, dataclass
import math
import torch
from torch import nn
import torch.nn.functional as F

class ByteTokenizer:
    vocab_size = 256
    def encode(self, text): return list(text.encode("utf-8"))
    def decode(self, ids): return bytes(max(0, min(255, int(i))) for i in ids).decode("utf-8", errors="ignore")

@dataclass
class GPTConfig:
    vocab_size: int = 256
    block_size: int = 256
    n_layer: int = 6
    n_head: int = 6
    n_embd: int = 384
    dropout: float = .1

class CausalSelfAttention(nn.Module):
    def __init__(self, cfg):
        super().__init__(); assert cfg.n_embd % cfg.n_head == 0
        self.heads=cfg.n_head; self.dim=cfg.n_embd//cfg.n_head
        self.qkv=nn.Linear(cfg.n_embd,3*cfg.n_embd); self.proj=nn.Linear(cfg.n_embd,cfg.n_embd); self.drop=nn.Dropout(cfg.dropout)
        self.register_buffer("mask", torch.tril(torch.ones(cfg.block_size,cfg.block_size,dtype=torch.bool))[None,None])
    def forward(self,x):
        b,t,c=x.shape; q,k,v=self.qkv(x).chunk(3,-1); shape=(b,t,self.heads,self.dim)
        q=q.view(*shape).transpose(1,2); k=k.view(*shape).transpose(1,2); v=v.view(*shape).transpose(1,2)
        scores=(q@k.transpose(-2,-1))/math.sqrt(self.dim); scores=scores.masked_fill(~self.mask[:,:,:t,:t],torch.finfo(scores.dtype).min)
        weights=self.drop(F.softmax(scores,-1)); return self.drop(self.proj((weights@v).transpose(1,2).contiguous().view(b,t,c)))

class Block(nn.Module):
    def __init__(self,cfg):
        super().__init__(); self.ln1=nn.LayerNorm(cfg.n_embd); self.attn=CausalSelfAttention(cfg); self.ln2=nn.LayerNorm(cfg.n_embd)
        self.mlp=nn.Sequential(nn.Linear(cfg.n_embd,4*cfg.n_embd),nn.GELU(),nn.Linear(4*cfg.n_embd,cfg.n_embd),nn.Dropout(cfg.dropout))
    def forward(self,x):
        x=x+self.attn(self.ln1(x)); return x+self.mlp(self.ln2(x))

class LocalGPT(nn.Module):
    def __init__(self,cfg):
        super().__init__(); self.cfg=cfg
        self.wte=nn.Embedding(cfg.vocab_size,cfg.n_embd); self.wpe=nn.Embedding(cfg.block_size,cfg.n_embd); self.drop=nn.Dropout(cfg.dropout)
        self.blocks=nn.ModuleList([Block(cfg) for _ in range(cfg.n_layer)]); self.ln=nn.LayerNorm(cfg.n_embd); self.head=nn.Linear(cfg.n_embd,cfg.vocab_size,bias=False); self.head.weight=self.wte.weight
        self.apply(self._init)
    def _init(self,m):
        if isinstance(m,(nn.Linear,nn.Embedding)):
            nn.init.normal_(m.weight,0,.02)
            if isinstance(m,nn.Linear) and m.bias is not None: nn.init.zeros_(m.bias)
    def forward(self,idx,targets=None):
        b,t=idx.shape
        if t>self.cfg.block_size: raise ValueError("input is longer than block_size")
        pos=torch.arange(t,device=idx.device); x=self.drop(self.wte(idx)+self.wpe(pos))
        for block in self.blocks: x=block(x)
        logits=self.head(self.ln(x)); loss=None if targets is None else F.cross_entropy(logits.reshape(-1,logits.size(-1)),targets.reshape(-1)); return logits,loss
    @torch.no_grad()
    def generate(self,idx,max_new_tokens,temperature=.8,top_k=40,top_p=.92):
        self.eval()
        for _ in range(max_new_tokens):
            logits,_=self(idx[:,-self.cfg.block_size:]); logits=logits[:,-1,:]/max(float(temperature),1e-5)
            if top_k>0:
                values,indices=torch.topk(logits,min(top_k,logits.size(-1))); filtered=torch.full_like(logits,float('-inf')); filtered.scatter_(1,indices,values); logits=filtered
            probs=F.softmax(logits,-1); sorted_probs,sorted_ids=torch.sort(probs,descending=True); keep=(sorted_probs.cumsum(-1)-sorted_probs)<=top_p; sorted_probs=sorted_probs*keep; sorted_probs/=sorted_probs.sum(-1,keepdim=True).clamp_min(1e-9)
            idx=torch.cat((idx,sorted_ids.gather(1,torch.multinomial(sorted_probs,1))),1)
        return idx
    def config_dict(self): return asdict(self.cfg)

def save_checkpoint(model,path): torch.save({"config":model.config_dict(),"model_state":model.state_dict()},path)
def load_checkpoint(path,device="cpu"):
    data=torch.load(path,map_location=device); model=LocalGPT(GPTConfig(**data["config"])).to(device); model.load_state_dict(data["model_state"]); model.eval(); return model
