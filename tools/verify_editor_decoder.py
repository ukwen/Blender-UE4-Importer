"""Verify a separately built helper against pinned ShooterSam payloads and corrupt inputs.
Standard library only; use trusted original fixtures. Does not run Unreal or Blender.
"""
import argparse, hashlib, json, struct, subprocess, sys, zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_blueprint import read_tables
from ue5_editor_payload import read_trailer, extract_payload

FIXTURES=(
 ('LevelPrototyping/Interactable/Door/Assets/Meshes/SM_Door.uasset','26a7645f404dda23a1e4c8d20d7940473f208fee1d5f679581bc3842aa6d7499','14447b0cd10a69a4e0897702fc1c179bbb1931fc',3998,'08d2fd6525a1951b0b2caf414a17b59b39e5eaf4c4a0772f0efc30a191ec8a9c'),
 ('Characters/Mannequins/Meshes/SKM_Quinn_Simple.uasset','1ef45d92507a76d74a5e06737f94cad40eb7d5f5769dfbb63f7f74e784a178c6','68219ae621badad6de2c088f85b4398897db7572',19699739,'109be466f5b083497f7a6661897a8363275b44eaf34c251319e11257d0cc352b'),
 ('Characters/Mannequins/Textures/Quinn/T_Quinn_01_D.uasset','04e5ed207b7df0d2ad1bbc668916bcf170545fc2a72875e49ec99c6e2667002f','8e02c48ab201876a21aad3e9ebb83b41c6344a31',4194304,'48175aee28d441166b933a0a5341b1d38dc1685aa0d2615ab20946d2af8ee6a7'),
 ('MyStuff/EnemyCharacter/Textures/T_EnemySkull_Mask.uasset','75721f37d7c1acd862ad55f22ca2781c5ece269725483112dc31e0d72e449631','a38cc6de2813bac1db3a78e46ef1fb915a52f5f5',6290064,'cc0ef3ba82997ba5e2fe387564a8796f6558f36a27591ee94618b9a80569d294'),
)

def check(ok,message):
    if not ok: raise ValueError(message)

def main():
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('decoder',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    root=a.project.resolve().parent/'Content';exe=str(a.decoder.resolve());rows=[]
    for rel,src_hash,digest,size,decoded_hash in FIXTURES:
        _,raw,_,ex,*_=read_tables(root/rel);check(hashlib.sha256(raw).hexdigest()==src_hash,'Unexpected fixture revision '+rel)
        records=read_trailer(raw,max(x['offset']+x['size'] for x in ex));data,info=extract_payload(raw,records,digest,size,exe)
        check(len(data)==size and hashlib.sha256(data).hexdigest()==decoded_hash,'Decoded hash mismatch '+rel)
        rows.append(dict(file=rel,bytes=size,sha256=decoded_hash,method=info['method']));print('PASS',rel,size,flush=True)
        if len(rows)==1:
            r=records[digest];buf=bytearray(raw[r['offset']:r['offset']+r['stored']]);buf[4]^=1
            result=subprocess.run([exe],input=buf,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            check(result.returncode!=0 and not result.stdout,'Corrupt CRC accepted')
            # Encode a method 0 buffer with the real validated BLAKE3 of the source.
            header=bytearray(struct.pack('>II4BIQQ',0xb7756362,0,0,0,0,0,1,len(data),64+len(data))+bytes.fromhex(info['hash']))
            struct.pack_into('>I',header,4,zlib.crc32(header[8:])&0xffffffff)
            valid=bytes(header)+data;result=subprocess.run([exe],input=valid,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            check(result.returncode==0 and result.stdout==data,'Uncompressed binary stream mismatch')
            invalid=bytearray(valid);invalid[-1]^=1;result=subprocess.run([exe],input=invalid,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            check(result.returncode!=0 and not result.stdout,'Corrupt payload accepted')
    report=dict(platform=sys.platform,fixtures=rows,uncompressed_binary=True,corrupt_crc_rejected=True,corrupt_payload_rejected=True)
    if a.report:a.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
