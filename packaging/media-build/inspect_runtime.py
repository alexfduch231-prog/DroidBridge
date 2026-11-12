"""Record PE import closure, hashes and private-build-path scan for every runtime."""
from pathlib import Path
import subprocess, json, re, hashlib
root=Path(__file__).resolve().parents[1]; work=root/'.build/media-minimal-01'; kit=work/'media-kit'; binary=kit/'bin'
objdump=root/'.build-tools/media/w64devkit/bin/objdump.exe'
entries={}; privacy=[]; unresolved=[]
# Explicit Windows API DLLs; no arbitrary DLL is accepted merely because installed locally.
system=set('advapi32 bcrypt cfgmgr32 comctl32 comdlg32 crypt32 d3d11 d3d12 d3d9 dcomp dinput8 dnsapi dwmapi dxgi gdi32 hid imm32 iphlpapi kernel32 msvcrt ntdll ole32 oleaut32 opengl32 powrprof propsys psapi rpcrt4 secur32 setupapi shell32 shlwapi user32 userenv usp10 uxtheme version winmm winspool wintrust ws2_32 wtsapi32'.split())
provided={p.name.lower() for p in binary.iterdir()}
for p in sorted(binary.iterdir()):
    data=p.read_bytes()
    private_root=root.parents[1].as_posix()
    patterns=[private_root,private_root.replace('/',chr(92)), '/'+private_root[0].lower()+private_root[2:]]
    users='/'.join(('C:','Users',''))
    patterns += [users,users.replace('/',chr(92))]
    for text in patterns:
        if any(text.lower().encode(enc) in data.lower() for enc in ('utf8','utf-16le')): privacy.append({'file':p.name,'pattern':text})
    result=subprocess.run([str(objdump),'-p',str(p)],capture_output=True,text=True,check=True)
    imports=re.findall(r'DLL Name:\s*(\S+)',result.stdout)
    assert imports, ('no imports parsed',p.name)
    for dll in imports:
        name=dll.lower()
        if name not in provided and name.removesuffix('.dll') not in system and not name.startswith(('api-ms-win-','ext-ms-win-')):
            unresolved.append({'file':p.name,'dll':dll})
    entries[p.name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'imports':imports}
report={'runtime':entries,'private_paths':privacy,'unresolved_imports':unresolved}
(work/'runtime-inspection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
assert not privacy, privacy
assert not unresolved, unresolved
