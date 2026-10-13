// Raster assets use nearest-neighbor scaling; SVG paths retain the game font.
const fs=require('fs');
const path=require('path');
const sharp=require(process.env.H3_COVER_SHARP || 'sharp');

async function main(){
  const folder=path.resolve(process.argv[2]);
  for(const ratio of ['16x9','4x3']){
    let svg=fs.readFileSync(path.join(folder,`cover-${ratio}.layout.svg`),'utf8');
    const matches=[...svg.matchAll(/ASSET:(\w+):(\d+):(\d+)/g)];
    for(const [token,name,w,h] of matches){
      let input=sharp(path.join(folder,'assets',name+'.png'));
      const buffer=await input.resize(Number(w),Number(h),{kernel:sharp.kernel.nearest,fit:'fill'}).png().toBuffer();
      svg=svg.replace(token,'data:image/png;base64,'+buffer.toString('base64'));
    }
    fs.writeFileSync(path.join(folder,`cover-${ratio}.svg`),svg);
    await sharp(Buffer.from(svg)).png().toFile(path.join(folder,`cover-${ratio}.png`));
    // Thumbnail QA artifact is deliberately scaled with nearest-neighbor too.
    await sharp(path.join(folder,`cover-${ratio}.png`)).resize(640,null,{kernel:sharp.kernel.nearest}).png().toFile(path.join(folder,`cover-${ratio}.preview.png`));
    console.log(ratio,await sharp(path.join(folder,`cover-${ratio}.png`)).metadata());
  }
}
main().catch(e=>{console.error(e);process.exit(1)});
