"""The APIHealer web page (HTML/CSS/JS as one string).

Kept separate from web.py so the server file stays about serving, not markup.
Design direction: a "diagnostic report" -- APIHealer inspects a patient (your
code against a contract) and issues findings with an evidence level. Calm,
clinical, trustworthy; the confidence signal is the one bold element.
"""

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APIHealer</title>
<style>
  :root{
    --ink:#12211f; --paper:#f6f4ee; --card:#fffdf8; --line:#dcd7ca;
    --muted:#5c6764; --teal:#0f6e63; --teal-deep:#0a4b43;
    --amber:#b7791f; --red:#a23b2d; --green:#2f7d4f;
    --shadow:0 1px 0 rgba(0,0,0,.04),0 8px 24px -18px rgba(15,110,99,.35);
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    margin:0;background:var(--paper);color:var(--ink);
    font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
    line-height:1.55;
  }
  .wrap{max-width:940px;margin:0 auto;padding:0 22px}
  code,kbd,.mono{font-family:"SF Mono",ui-monospace,"Cascadia Code",Menlo,Consolas,monospace}

  header.top{border-bottom:1px solid var(--line);background:var(--card)}
  .top .wrap{display:flex;align-items:center;justify-content:space-between;
    padding:16px 22px}
  .brand{display:flex;align-items:baseline;gap:10px}
  .brand .mark{font-size:26px;font-weight:700;letter-spacing:-.02em;color:var(--teal-deep)}
  .brand .tag{font-size:13px;color:var(--muted);font-style:italic}
  nav a{color:var(--teal-deep);text-decoration:none;font-size:14px;margin-left:18px;
    border-bottom:1px solid transparent;padding-bottom:2px}
  nav a:hover{border-color:var(--teal)}

  .hero{padding:46px 0 26px}
  .hero h1{font-size:34px;line-height:1.15;margin:0 0 10px;letter-spacing:-.015em;max-width:20ch}
  .hero p{font-size:17px;color:var(--muted);margin:0;max-width:58ch}
  .hero .rule{width:54px;height:3px;background:var(--teal);margin:20px 0 0;border-radius:2px}

  section{padding:26px 0}
  h2.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.14em;
    color:var(--teal-deep);margin:0 0 14px;font-family:inherit;font-weight:700}

  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:22px;box-shadow:var(--shadow)}

  /* form */
  .field{margin-bottom:16px}
  .field label{display:block;font-size:14px;font-weight:700;margin-bottom:6px}
  .field .hint{font-size:13px;color:var(--muted);margin:0 0 8px;font-style:italic}
  .field input[type=text]{width:100%;padding:11px 13px;border:1px solid var(--line);
    border-radius:9px;font-size:15px;background:#fffefb;font-family:inherit}
  .field input:focus{outline:2px solid var(--teal);border-color:var(--teal)}
  .row{display:flex;gap:16px;flex-wrap:wrap}
  .row .field{flex:1;min-width:220px}
  .check{display:flex;align-items:flex-start;gap:10px;font-size:14px}
  .check input{margin-top:4px}
  .check .hint{margin:2px 0 0}

  .btn{appearance:none;border:0;border-radius:10px;padding:13px 22px;font-size:16px;
    font-weight:700;color:#fff;background:var(--teal);cursor:pointer;font-family:inherit;
    box-shadow:0 1px 0 rgba(0,0,0,.06)}
  .btn:hover{background:var(--teal-deep)}
  .btn:disabled{opacity:.55;cursor:progress}

  /* steps list */
  ol.steps{counter-reset:s;list-style:none;padding:0;margin:0}
  ol.steps li{counter-increment:s;position:relative;padding:12px 0 12px 46px;
    border-bottom:1px solid var(--line)}
  ol.steps li:last-child{border-bottom:0}
  ol.steps li::before{content:counter(s);position:absolute;left:0;top:11px;
    width:30px;height:30px;border-radius:50%;background:var(--paper);
    border:1px solid var(--teal);color:var(--teal-deep);font-weight:700;
    display:flex;align-items:center;justify-content:center;font-size:14px}
  ol.steps b{display:block}
  ol.steps .mono{font-size:13px;color:var(--muted)}

  /* result */
  #result{margin-top:20px;display:none}
  .verdict{display:flex;align-items:center;gap:16px;flex-wrap:wrap;
    padding:18px 20px;border-radius:12px;border:1px solid var(--line);margin-bottom:16px}
  .dial{--p:0;width:74px;height:74px;border-radius:50%;flex:0 0 auto;
    background:conic-gradient(currentColor calc(var(--p)*1%),#e7e2d6 0);
    display:flex;align-items:center;justify-content:center;position:relative}
  .dial::after{content:"";position:absolute;inset:9px;background:var(--card);border-radius:50%}
  .dial span{position:relative;z-index:1;font-weight:700;font-size:18px}
  .verdict .vmain{flex:1;min-width:200px}
  .verdict .vmain .big{font-size:20px;font-weight:700;margin:0}
  .verdict .vmain .sub{font-size:14px;color:var(--muted);margin:3px 0 0}
  .badge{display:inline-block;font-size:12px;font-weight:700;padding:3px 10px;
    border-radius:999px;text-transform:uppercase;letter-spacing:.06em}
  .b-teal{background:#e2efeec;color:var(--teal-deep)}
  .b-high{color:var(--green)} .b-med{color:var(--amber)} .b-low{color:var(--red)}

  .panel{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:14px}
  .panel h3{margin:0;padding:11px 16px;font-size:13px;text-transform:uppercase;
    letter-spacing:.1em;background:#f0ede4;border-bottom:1px solid var(--line)}
  .panel .body{padding:14px 16px}
  .panel ul{margin:0;padding-left:20px}
  .panel li{margin:5px 0}
  .risk li::marker{color:var(--amber)}
  .evi li::marker{color:var(--green)}
  .files code{background:#eef4f2;padding:2px 7px;border-radius:6px;font-size:13px}
  .report{white-space:pre-wrap;font-size:13px;color:var(--muted);margin:0}

  .note{font-size:14px;padding:12px 15px;border-radius:10px;border:1px solid var(--line);
    background:#fbf7ea}
  .note.err{background:#fbeeeb;border-color:#e6c3bb;color:var(--red)}

  footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px;
    padding:26px 0;margin-top:20px}
  .hide{display:none}

  details.faq{border:1px solid var(--line);border-radius:10px;padding:0 16px;margin-bottom:10px;background:var(--card)}
  details.faq summary{cursor:pointer;padding:13px 0;font-weight:700;font-size:15px}
  details.faq p{margin:0 0 14px;color:var(--muted)}
  @media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style>
</head>
<body>

<header class="top">
  <div class="wrap">
    <div class="brand">
      <span class="mark">APIHealer</span>
      <span class="tag">contract change, diagnosed &amp; repaired</span>
    </div>
    <nav>
      <a href="#run">Run</a>
      <a href="#how">How it works</a>
      <a href="#help">Help</a>
    </nav>
  </div>
</header>

<div class="wrap">

  <div class="hero">
    <h1>When an API you depend on changes, find out and fix it &mdash; with the receipts.</h1>
    <p>APIHealer checks a live API contract against the last one it saw, repairs
       the code that breaks, and tells you exactly how much of that repair it can
       prove. Everything runs on your machine.</p>
    <div class="rule"></div>
  </div>

  <section id="run">
    <h2 class="eyebrow">Run a check</h2>
    <div class="card">
      <div class="field">
        <label for="path">Project folder</label>
        <p class="hint">The full path to the project that consumes the API
           (the folder with your .csproj).</p>
        <input type="text" id="path" placeholder="C:\repos\my-project\Client">
      </div>
      <div class="row">
        <div class="field">
          <label for="url">Contract (Swagger) URL</label>
          <p class="hint">Where the API publishes its OpenAPI/Swagger JSON.</p>
          <input type="text" id="url" placeholder="http://localhost:5080/swagger/v1/swagger.json">
        </div>
        <div class="field">
          <label for="name">Name for this API</label>
          <p class="hint">So one project can watch several APIs. e.g. <code>orders</code>.</p>
          <input type="text" id="name" placeholder="orders">
        </div>
      </div>
      <div class="field check">
        <input type="checkbox" id="apply">
        <label for="apply" style="font-weight:400">
          <b>Apply the fix to my files.</b>
          <span class="hint">Leave off to preview only. When on, APIHealer writes the
          repaired code (staged safely &mdash; a failed multi-file fix rolls back).</span>
        </label>
      </div>
      <button class="btn" id="go">Check &amp; repair</button>
      <p class="hint" id="llmhint" style="margin-top:12px"></p>
    </div>

    <div id="result"></div>
  </section>

  <section id="how">
    <h2 class="eyebrow">How it works</h2>
    <div class="card">
      <p style="margin-top:0;color:var(--muted)">
        APIHealer leans on real tools where they exist and treats the AI as an
        assistant whose output is <em>verified</em>, not trusted blindly. One pass
        does this:</p>
      <ol class="steps">
        <li><b>Read the contract</b><span class="mono">downloads the Swagger and compares it to the saved baseline (oasdiff)</span></li>
        <li><b>Decide the client type</b><span class="mono">generated (NSwag/Kiota) or hand-written &mdash; this sets how much can be proven</span></li>
        <li><b>Regenerate &amp; build</b><span class="mono">for generated clients, the compiler pinpoints every broken line</span></li>
        <li><b>Repair</b><span class="mono">the LLM adapts only the affected code</span></li>
        <li><b>Verify</b><span class="mono">recompiles to confirm the fix, and reports what a passing build still can't prove</span></li>
      </ol>
    </div>
  </section>

  <section id="help">
    <h2 class="eyebrow">Help</h2>

    <details class="faq" open>
      <summary>First time with a new API &mdash; what happens?</summary>
      <p>The first run just saves a <em>baseline</em>: the current contract, so
      later runs have something to compare against. You'll see &ldquo;baseline
      saved.&rdquo; Run it again after the API changes to detect and repair.</p>
    </details>

    <details class="faq">
      <summary>What do the confidence levels mean?</summary>
      <p><b>High</b> &mdash; a generated client was regenerated and the project
      recompiled: the code fits the new contract's types. <b>Medium/Low</b> &mdash;
      a hand-written client: the fix compiles, but compiling can't prove the
      contract mapping is right. APIHealer always lists what a pass does
      <em>not</em> prove.</p>
    </details>

    <details class="faq">
      <summary>Do I need an AI key?</summary>
      <p>To <em>apply</em> a repair, yes &mdash; set <code>ANTHROPIC_API_KEY</code>
      (Claude) or run a local Ollama, and set <code>APIHEALER_LLM</code>. Without
      one, APIHealer still detects the change and points at the exact spots to fix.
      Your key stays in your environment; it never touches the code or the repo.</p>
    </details>

    <details class="faq">
      <summary>Where does it store the baseline?</summary>
      <p>In <code>.apihealer/&lt;name&gt;/contract.json</code> inside the project.
      Commit that folder so a clean CI runner shares the same baseline. Only the
      temporary download is ignored.</p>
    </details>

    <details class="faq">
      <summary>Is anything sent anywhere?</summary>
      <p>The tool runs locally. It fetches the contract URL you give it, and &mdash;
      only if you apply a fix &mdash; sends the affected code to the LLM you chose.
      Nothing else leaves your machine.</p>
    </details>
  </section>

  <footer>
    APIHealer runs locally on your machine. Close the terminal window to stop the server.
  </footer>
</div>

<script>
  // Show which LLM providers are wired up.
  fetch('/api/providers').then(r=>r.json()).then(d=>{
    const el=document.getElementById('llmhint');
    if(d.providers&&d.providers.length){
      el.innerHTML='Repair uses your configured LLM ('+d.providers.join(', ')+
        '). Set <code>APIHEALER_LLM</code> and its key before applying.';
    }
  }).catch(()=>{});

  const $=id=>document.getElementById(id);
  const confClass=p=>p>=0.8?'b-high':(p>=0.45?'b-med':'b-low');
  const confWord=p=>p>=0.8?'High':(p>=0.45?'Medium':'Low');
  const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

  function panel(title,inner,cls){
    return '<div class="panel"><h3>'+title+'</h3><div class="body '+(cls||'')+'">'+inner+'</div></div>';
  }
  function list(items,cls){
    if(!items||!items.length) return '';
    return '<ul class="'+(cls||'')+'">'+items.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul>';
  }

  function render(d){
    const box=$('result'); box.style.display='block';
    if(!d.ok){
      box.innerHTML='<div class="note err"><b>Can\u2019t run yet.</b> '+esc(d.message)+'</div>';
      box.scrollIntoView({behavior:'smooth',block:'start'}); return;
    }
    // context line always
    let head='<div class="note">Project client type: <b>'+esc(d.client_kind)+
      '</b>. '+esc((d.client_reasons||[]).join(' '))+'</div>';

    if(d.stage==='baseline'||d.stage==='nochange'||d.stage==='nonbreaking'){
      box.innerHTML=head+'<div class="note" style="margin-top:12px">'+esc(d.message)+'</div>';
      box.scrollIntoView({behavior:'smooth',block:'start'}); return;
    }

    // remediated
    const r=d.result, v=r.verification, p=r.confidence||0;
    const dial='<div class="dial '+confClass(p)+'" style="--p:'+Math.round(p*100)+
      '"><span>'+Math.round(p*100)+'%</span></div>';
    const applied=r.applied?'Applied to your files':'Preview only (not written)';
    const verdict='<div class="verdict">'+dial+
      '<div class="vmain"><p class="big">'+confWord(p)+' confidence &mdash; <span class="mono">'+
      esc(v.level)+'</span></p><p class="sub">'+applied+
      (d.had_llm?'':' &middot; no LLM configured, so this is detection only')+
      '</p></div></div>';

    let body=head+verdict;
    if(r.files_changed&&r.files_changed.length){
      body+=panel('Files',(r.files_changed.map(f=>'<code>'+esc(f)+'</code>').join(' ')),'files');
    }
    if(v.evidence&&v.evidence.length) body+=panel('Evidence',list(v.evidence,'evi'));
    if(v.remaining_risks&&v.remaining_risks.length)
      body+=panel('What a passing build still can\u2019t prove',list(v.remaining_risks,'risk'));
    if(d.breaking_report) body+=panel('Contract changes','<p class="report">'+esc(d.breaking_report)+'</p>');

    box.innerHTML=body;
    box.scrollIntoView({behavior:'smooth',block:'start'});
  }

  $('go').addEventListener('click',()=>{
    const btn=$('go'); btn.disabled=true; btn.textContent='Working\u2026';
    fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        path:$('path').value, swagger_url:$('url').value,
        name:$('name').value, apply:$('apply').checked
      })
    }).then(r=>r.json()).then(render)
      .catch(e=>render({ok:false,message:String(e)}))
      .finally(()=>{btn.disabled=false;btn.textContent='Check & repair';});
  });
</script>
</body>
</html>
"""
