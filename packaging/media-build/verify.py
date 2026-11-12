"""Strict runtime capability/synthetic roundtrip gate; never records desktop pixels."""
import os, subprocess, pathlib, json, re
root=pathlib.Path(__file__).resolve().parents[1]
work=root/'.build/media-minimal-01'
bin=work/'media-kit/bin'
f=str(bin/'ffmpeg.exe'); p=str(bin/'ffplay.exe')
results=[]
def run(args, timeout=30, env=None):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,env=env)
    results.append({'args':args[1:],'exit':r.returncode,'output':r.stdout.decode('utf8','replace')})
    if r.returncode: raise RuntimeError(results[-1])
    return results[-1]['output']
try:
    for opt, names in [('-decoders',['h264','aac','pcm_s16le']),('-encoders',['h264_nvenc','pcm_s16le']),('-filters',['ddagrab','hwdownload','format','scale']),('-bsfs',['h264_metadata']),('-demuxers',['h264','aac','s16le'])]:
        text=run([f,'-hide_banner',opt])
        for n in names: assert re.search(r'\b'+n+r'\b',text), (opt,n)
    sample=str(work/'synthetic.h264')
    run([f,'-hide_banner','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=15','-t','0.5','-c:v','h264_nvenc','-preset','p1','-tune','ll','-rc','cbr','-b:v','6M','-maxrate','6M','-bufsize','3M','-g','15','-bf','0','-bsf:v','h264_metadata=aud=insert','-f','h264',sample])
    run([f,'-hide_banner','-f','h264','-i',sample,'-f','null','-'])
    env=os.environ.copy(); env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
    run([p,'-hide_banner','-autoexit','-f','h264',sample],env=env)
    for fmt, codec, suffix in [('adts','aac','aac'),('s16le','pcm_s16le','pcm')]:
        audio=str(work/('synthetic.'+suffix))
        run([f,'-hide_banner','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.3','-c:a',codec,'-f',fmt,audio])
        args=[p,'-hide_banner','-autoexit','-nodisp','-f','aac' if fmt=='adts' else fmt]
        if fmt=='s16le': args+=['-ar','48000','-ch_layout','mono']
        run(args+[audio],env=env)
    # Desktop capture deliberately not exercised: synthetic NVENC proves runtime driver use.
finally:
    (work/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf8')
print('ALL GATES PASSED')
