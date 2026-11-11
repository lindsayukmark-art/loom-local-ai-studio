"""Self-contained game projects generated locally, without executing their code.

These projects are HTML5 games for a Windows browser, not native executables.
The server must serve previews with the CSP below and an iframe sandbox that
allows scripts but neither same-origin access nor navigation of the parent.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


GAME_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; media-src data: blob:; connect-src 'none'; "
    "font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
)
MAX_GAME_BYTES = 200_000


class _OfflineHTML(HTMLParser):
    """Reject externally loaded resources; runtime network requests hit the CSP."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._title = False
        self.open_raw = {"script": 0, "style": 0}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in self.open_raw:
            self.open_raw[tag] += 1
        if tag in {"iframe", "frame", "frameset", "object", "embed", "base", "link", "form"}:
            raise ValueError(f"Game HTML cannot contain <{tag}> elements.")
        if tag == "meta" and attributes.get("http-equiv", "").lower() == "refresh":
            raise ValueError("Game HTML cannot redirect to another page.")
        for key, value in attrs:
            if key in {"src", "href", "poster", "action", "data", "srcset", "xlink:href"}:
                if value and not value.startswith(("data:", "blob:", "#")):
                    raise ValueError("Game assets must be embedded: external file URLs are disabled.")
        if tag == "title":
            self._title = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.open_raw:
            raise ValueError(f"Game HTML must close <{tag}> with an explicit end tag.")
        super().handle_startendtag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.open_raw:
            if self.open_raw[tag] == 0:
                raise ValueError(f"Game HTML has an unmatched </{tag}> tag.")
            self.open_raw[tag] -= 1
        if tag == "title":
            self._title = False

    def handle_data(self, data: str) -> None:
        if self._title:
            self.title += data


_STYLE = """
:root{color-scheme:dark;font-family:system-ui,Segoe UI,sans-serif;background:#0a1018;color:#edf5f4}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px}
main{width:min(100%,800px)}header{display:flex;align-items:end;justify-content:space-between;gap:16px}
h1{font-size:clamp(24px,5vw,36px);letter-spacing:-1px;margin:0}p{color:#9baeb9;line-height:1.5}
.eyebrow{color:#a1efce;letter-spacing:2px;font-size:11px;text-transform:uppercase}.score{text-align:right;font-size:14px;color:#a1efce}
canvas{width:100%;display:block;background:#0c1722;border:1px solid #2e424c;border-radius:16px;touch-action:none;outline:none}
canvas:focus-visible{outline:2px solid #a1efce;outline-offset:3px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
button{border:1px solid #354b53;background:#162831;color:#e6f8f1;padding:11px 18px;border-radius:9px;cursor:pointer;font:inherit}
button:first-child{background:#a1efce;color:#0c2320;border-color:#a1efce}button:hover{filter:brightness(1.12)}
.hint{font-size:13px}.status{min-height:24px;color:#a1efce}footer{font-size:11px;color:#6e858f;margin-top:20px}
"""


def _space_game() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Orbit Runner</title><style>""" + _STYLE + """</style></head><body><main>
<header><div><p class="eyebrow">Local game template · Loom</p><h1>Orbit Runner</h1></div><p class="score">SCORE <strong id="score">0</strong></p></header>
<p>Pilot a tiny ship through a meteor field. Keep your orbit for as long as you can.</p>
<canvas id="game" width="760" height="460" tabindex="0" aria-label="Orbit Runner game. Use arrow keys or A and D to move."></canvas>
<div class="controls"><button id="start">Start game</button><button id="pause">Pause</button><button id="restart">Restart</button></div>
<p id="status" class="status" role="status">Ready for launch.</p><p class="hint">Move: ← → or A / D. You can also drag on the field. Space pauses. Avoid every meteor.</p><footer>Self-contained HTML5 game · No downloads, accounts, or network connection required</footer>
</main><script>
"use strict";
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d'),scoreEl=document.getElementById('score'),statusEl=document.getElementById('status');
const W=canvas.width,H=canvas.height,keys=new Set();
let ship={x:W/2,y:H-47},rocks=[],elapsed=0,spawn=0,frame=0,seed=92731,running=false,paused=false,over=false,last=0;
function random(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;}
function draw(){
ctx.fillStyle='#0c1722';ctx.fillRect(0,0,W,H);
for(let i=0;i<64;i++){const x=(i*137.71)%W,y=(i*93.17+elapsed*14)%H;ctx.fillStyle=i%3?'#30505b':'#669b9b';ctx.fillRect(x,y,2,2);}
for(const rock of rocks){ctx.fillStyle='#bd8c76';ctx.beginPath();for(let i=0;i<7;i++){const a=i*Math.PI*2/7+rock.angle;const r=rock.r*(i%2?.87:1);const x=rock.x+Math.cos(a)*r,y=rock.y+Math.sin(a)*r;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();ctx.fill();ctx.strokeStyle='#e7b195';ctx.stroke();}
ctx.save();ctx.translate(ship.x,ship.y);ctx.fillStyle='#a1efce';ctx.beginPath();ctx.moveTo(0,-19);ctx.lineTo(15,17);ctx.lineTo(0,10);ctx.lineTo(-15,17);ctx.closePath();ctx.fill();ctx.fillStyle='#4eb9de';ctx.fillRect(-4,14,8,8+Math.sin(elapsed*28)*4);ctx.restore();
if(!running||paused){ctx.fillStyle='#071019ba';ctx.fillRect(0,0,W,H);ctx.textAlign='center';ctx.fillStyle='#e9fff4';ctx.font='bold 29px system-ui';ctx.fillText(over?'Flight complete':paused?'Flight paused':'Ready for launch',W/2,H/2-7);ctx.font='15px system-ui';ctx.fillStyle='#a5c0c3';ctx.fillText(over?'Press Restart to fly again':paused?'Press Pause or Space to continue':'Press Start game to begin',W/2,H/2+25);}
}
function reset(){ship={x:W/2,y:H-47};rocks=[];elapsed=0;spawn=0;frame=0;seed=92731;paused=false;over=false;scoreEl.textContent='0';}
function start(){reset();running=true;statusEl.textContent='Flight in progress — avoid the meteors.';canvas.focus();draw();}
function pause(){if(!running)return;paused=!paused;statusEl.textContent=paused?'Paused.':'Flight resumed.';draw();}
function tick(now){const dt=Math.min((now-last)/1000||0,.04);last=now;
if(running&&!paused){elapsed+=dt;spawn+=dt;const direction=(keys.has('ArrowRight')||keys.has('d')?1:0)-(keys.has('ArrowLeft')||keys.has('a')?1:0);ship.x=Math.max(20,Math.min(W-20,ship.x+direction*360*dt));
if(spawn>Math.max(.24,.8-elapsed*.008)){spawn=0;const r=13+random()*16;rocks.push({x:r+random()*(W-r*2),y:-40,r,speed:110+random()*70+elapsed*3,angle:random()*6});}
for(const rock of rocks){rock.y+=rock.speed*dt;rock.angle+=dt*.7;if(Math.hypot(rock.x-ship.x,rock.y-ship.y)<rock.r+11){running=false;over=true;statusEl.textContent='Flight complete! Score: '+Math.floor(elapsed*10)+'. Press Restart to try again.';}}
rocks=rocks.filter(r=>r.y<H+50);scoreEl.textContent=String(Math.floor(elapsed*10));}
draw();requestAnimationFrame(tick);}
document.getElementById('start').addEventListener('click',start);document.getElementById('restart').addEventListener('click',start);document.getElementById('pause').addEventListener('click',pause);
window.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight',' ','a','d','A','D'].includes(event.key)){event.preventDefault();if(event.key===' '&&!event.repeat)pause();keys.add(event.key.toLowerCase().startsWith('arrow')?event.key:event.key.toLowerCase());}});
window.addEventListener('keyup',event=>{keys.delete(event.key);keys.delete(event.key.toLowerCase());});window.addEventListener('blur',()=>{keys.clear();if(running&&!paused)pause();});
function move(event){const rect=canvas.getBoundingClientRect();ship.x=Math.max(20,Math.min(W-20,(event.clientX-rect.left)*W/rect.width));}
canvas.addEventListener('pointerdown',event=>{canvas.setPointerCapture(event.pointerId);move(event);});canvas.addEventListener('pointermove',event=>{if(event.buttons)move(event);});
reset();requestAnimationFrame(tick);
</script></body></html>"""


def _snake_game() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mint Snake</title><style>""" + _STYLE + """</style></head><body><main>
<header><div><p class="eyebrow">Local game template · Loom</p><h1>Mint Snake</h1></div><p class="score">SCORE <strong id="score">0</strong></p></header>
<p>A familiar little challenge. Eat the golden dots, grow longer, and stay inside the grid.</p>
<canvas id="game" width="600" height="480" tabindex="0" aria-label="Mint Snake game. Use arrows or W A S D to turn."></canvas>
<div class="controls"><button id="start">Start game</button><button id="pause">Pause</button><button id="restart">Restart</button><button data-dir="up" aria-label="Move up">↑</button><button data-dir="left" aria-label="Move left">←</button><button data-dir="down" aria-label="Move down">↓</button><button data-dir="right" aria-label="Move right">→</button></div>
<p id="status" class="status" role="status">Ready to play.</p><p class="hint">Turn: arrow keys or W A S D. Space pauses. Don’t hit a wall or your own tail.</p><footer>Self-contained HTML5 game · No downloads, accounts, or network connection required</footer>
</main><script>
"use strict";
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d'),statusEl=document.getElementById('status'),scoreEl=document.getElementById('score');
const cell=24,cols=25,rows=20,directions={up:{x:0,y:-1},down:{x:0,y:1},left:{x:-1,y:0},right:{x:1,y:0}};
let snake=[],direction={x:1,y:0},pending={x:1,y:0},food={x:18,y:10},score=0,running=false,paused=false,over=false,changed=false,seed=43917,last=0,accumulator=0;
function random(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;}
function newFood(){const free=[];for(let y=0;y<rows;y++)for(let x=0;x<cols;x++)if(!snake.some(p=>p.x===x&&p.y===y))free.push({x,y});if(!free.length){running=false;over=true;statusEl.textContent='You filled the grid. You win!';return;}food=free[Math.floor(random()*free.length)];}
function reset(){snake=[{x:8,y:10},{x:7,y:10},{x:6,y:10}];direction={x:1,y:0};pending={x:1,y:0};food={x:18,y:10};score=0;paused=false;over=false;changed=false;seed=43917;accumulator=0;scoreEl.textContent='0';}
function start(){reset();running=true;statusEl.textContent='Eat the golden dots. Keep growing.';canvas.focus();}
function pause(){if(!running)return;paused=!paused;statusEl.textContent=paused?'Paused.':'Game resumed.';}
function turn(name){const next=directions[name];if(!next||changed||next.x===-direction.x&&next.y===-direction.y)return;pending=next;changed=true;}
function step(){direction=pending;changed=false;const head={x:snake[0].x+direction.x,y:snake[0].y+direction.y};const eating=head.x===food.x&&head.y===food.y;
if(head.x<0||head.y<0||head.x>=cols||head.y>=rows||snake.slice(0,eating?snake.length:-1).some(p=>p.x===head.x&&p.y===head.y)){running=false;over=true;statusEl.textContent='Game over! Score: '+score+'. Press Restart to try again.';return;}
snake.unshift(head);if(eating){score+=10;scoreEl.textContent=String(score);newFood();}else snake.pop();}
function draw(){ctx.fillStyle='#0c1722';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.strokeStyle='#142833';for(let x=0;x<=cols;x++){ctx.beginPath();ctx.moveTo(x*cell,0);ctx.lineTo(x*cell,canvas.height);ctx.stroke();}for(let y=0;y<=rows;y++){ctx.beginPath();ctx.moveTo(0,y*cell);ctx.lineTo(canvas.width,y*cell);ctx.stroke();}
ctx.fillStyle='#f5ca77';ctx.beginPath();ctx.arc(food.x*cell+cell/2,food.y*cell+cell/2,7,0,Math.PI*2);ctx.fill();snake.forEach((p,i)=>{ctx.fillStyle=i?'#5dbd99':'#b6f8d9';ctx.fillRect(p.x*cell+2,p.y*cell+2,cell-4,cell-4);});
if(!running||paused){ctx.fillStyle='#071019c9';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#e9fff4';ctx.font='bold 29px system-ui';ctx.textAlign='center';ctx.fillText(over?'Game over':paused?'Paused':'Mint Snake',canvas.width/2,canvas.height/2-7);ctx.font='15px system-ui';ctx.fillStyle='#a5c0c3';ctx.fillText(over?'Press Restart to play again':paused?'Press Space or Pause to continue':'Press Start game to begin',canvas.width/2,canvas.height/2+25);}}
function tick(now){const dt=Math.min(now-last||0,200);last=now;if(running&&!paused){accumulator+=dt;const interval=Math.max(70,150-score*.35);if(accumulator>=interval){accumulator=0;step();}}draw();requestAnimationFrame(tick);}
document.getElementById('start').addEventListener('click',start);document.getElementById('restart').addEventListener('click',start);document.getElementById('pause').addEventListener('click',pause);document.querySelectorAll('[data-dir]').forEach(button=>button.addEventListener('click',()=>turn(button.dataset.dir)));
window.addEventListener('keydown',event=>{const map={ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',w:'up',s:'down',a:'left',d:'right'};const name=map[event.key]||map[event.key.toLowerCase()];if(name){event.preventDefault();turn(name);}if(event.key===' '){event.preventDefault();if(!event.repeat)pause();}});
window.addEventListener('blur',()=>{if(running&&!paused)pause();});reset();requestAnimationFrame(tick);
</script></body></html>"""


def create_game(prompt: str, destination: Path, html_source: str | None = None) -> dict:
    """Write a local HTML game, validating model output before saving it.

    No generated JavaScript is executed by Python. A template is selected only
    when html_source is None; malformed model output fails rather than being
    silently replaced by a template.
    """
    if destination.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Game destination must be an HTML file.")
    mode = "template" if html_source is None else "local_model"
    source = (_snake_game() if "snake" in prompt.lower() else _space_game()) if html_source is None else html_source.strip()
    fenced = re.search(r"```(?:html)?\s*\n([\s\S]*?)```", source, re.IGNORECASE)
    if fenced:
        source = fenced.group(1).strip()
    if len(source.encode("utf-8")) > MAX_GAME_BYTES:
        raise ValueError("Game HTML exceeds the 200 KB project limit.")
    if not re.match(r"\s*(?:<!doctype\s+html[^>]*>\s*)?<html(?:\s|>)", source, re.IGNORECASE):
        raise ValueError("The local model must return a complete HTML document.")
    if not re.search(r"</html>\s*$", source, re.IGNORECASE):
        raise ValueError("Game HTML is incomplete: a closing </html> tag is required.")
    parser = _OfflineHTML()
    parser.feed(source)
    parser.close()
    if any(parser.open_raw.values()):
        raise ValueError("Game HTML is incomplete: every script and style needs a closing tag.")
    if re.search(r"https?://|wss?://|file://", source, re.IGNORECASE):
        raise ValueError("Game HTML contains an external URL. Only self-contained games are supported.")
    source = re.sub(r"^\s*<!doctype\s+html[^>]*>", "", source, count=1, flags=re.IGNORECASE)
    # Put the policy before every element supplied by a model. The implied head
    # is accepted by HTML parsers; a later <head> does not weaken this policy.
    policy = f'<!doctype html>\n<meta http-equiv="Content-Security-Policy" content="{html.escape(GAME_CSP, quote=True)}">\n'
    document = policy + source.lstrip()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return {"title": parser.title.strip()[:160] or "Local Game", "mode": mode, "kind": "game", "mime": "text/html", "bytes": len(document.encode("utf-8"))}


def create_game_bundle(html_path: Path, zip_path: Path) -> None:
    """Export a fixed-layout Windows browser game project, with no executable."""
    if not html_path.is_file() or html_path.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("A completed HTML game is required before export.")
    if html_path.stat().st_size > MAX_GAME_BYTES + 2048:
        raise ValueError("Game project exceeds the export limit.")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    readme = (
        "LOOM LOCAL GAME PROJECT\r\n\r\n"
        "This is a self-contained HTML5 game for a modern Windows browser.\r\n"
        "Extract all files, then double-click game.html or Play.cmd to play.\r\n"
        "No internet connection, Python installation, or game account is required.\r\n"
        "It is a browser game project, not a compiled Windows EXE.\r\n\r\n"
        "You can edit game.html in a text editor to change its code.\r\n"
        "Model-generated JavaScript is untrusted code; review it before executing or sharing.\r\n"
        "The app preview sandbox is absent when this downloaded HTML runs standalone.\r\n"
        "Its CSP and URL checks do not guarantee that all dynamically constructed\r\n"
        "navigation is blocked. Disconnect the computer to guarantee offline play.\r\n"
    )
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("game.html", html_path.read_bytes())
        archive.writestr("Play.cmd", '@echo off\r\nstart "" "%~dp0game.html"\r\n')
        archive.writestr("README.txt", readme)
