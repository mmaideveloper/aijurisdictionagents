param([Parameter(Mandatory = $true)][string]$FfmpegPath)
$ErrorActionPreference = 'Stop'
$ffmpeg = (Resolve-Path -LiteralPath $FfmpegPath).Path
Push-Location $PSScriptRoot
try {
    # Narration is the saved, newly synthesized Slovak female voice.
    $filters = @'
[0:v]scale=430:714,setsar=1[presenter];
[1:v]crop=482:577:385:127,scale=680:-2,setsar=1[form];
[2:v]scale=900:900,setsar=1[logo];
color=c=white:s=1080x1920:r=30:d=15[base];
[base][presenter]overlay=x=300:y=830:enable='lt(t,3.67)'[p];
[p][form]overlay=x=175:y=475:enable='gte(t,3.67)*lt(t,6.8)'[f];
[f]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,10.68)'[end];
[end][logo]overlay=x=65:y=370:enable='gte(t,10.68)'[branded];
[branded]ass=titles.ass,format=yuv420p[v];
[3:a]apad=whole_dur=15,atrim=duration=15,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]
'@
    & $ffmpeg -hide_banner -y -i presenter-lipsync.mp4 `
        -loop 1 -i registration-source.jpg -loop 1 -i ../assets/logo-black-hires.png `
        -i narration-viktoria.mp3 `
        -filter_complex $filters -map '[v]' -map '[a]' -t 15 -r 30 `
        -c:v libx264 -preset medium -crf 19 -c:a aac -b:a 128k -movflags +faststart registracia-sk.mp4
    if ($LASTEXITCODE -ne 0) { throw 'Video rendering failed.' }
    & $ffmpeg -hide_banner -v error -i registracia-sk.mp4 -f null -
    if ($LASTEXITCODE -ne 0) { throw 'Video decode validation failed.' }
    & $ffmpeg -hide_banner -v error -y -ss 13 -i registracia-sk.mp4 -frames:v 1 poster.png
    if ($LASTEXITCODE -ne 0) { throw 'Poster generation failed.' }
} finally { Pop-Location }
