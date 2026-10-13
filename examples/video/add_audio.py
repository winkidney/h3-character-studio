"""Add user-provided BGM without re-encoding the validated video stream."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def video_hash(path):
    return subprocess.check_output(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(path),
        '-map', '0:v:0', '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--title')
    parser.add_argument('--lufs', type=float, default=-18)
    parser.add_argument('--fade-in', type=float, default=.6)
    parser.add_argument('--fade-out', type=float, default=4)
    args = parser.parse_args()
    video, audio, output = args.video.resolve(), args.audio.resolve(), args.output.resolve()
    if not video.is_file() or not audio.is_file():
        parser.error('需要现有视频和用户提供的音频文件')
    if output.exists():
        parser.error('输出已存在，请使用新的文件名以保留旧版')
    source_video, source_audio = probe(video), probe(audio)
    duration = float(source_video['format']['duration'])
    if not -30 <= args.lufs <= -10 or min(args.fade_in, args.fade_out) < 0 or args.fade_in + args.fade_out > duration:
        parser.error('响度或淡入淡出范围无效')
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = [f'atrim=duration={duration:g}', f'apad=whole_dur={duration:g}']
    if args.fade_in:
        filters.append(f'afade=t=in:st=0:d={args.fade_in:g}')
    if args.fade_out:
        filters.append(f'afade=t=out:st={duration-args.fade_out:g}:d={args.fade_out:g}')
    base = ','.join(filters)
    analysis = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(audio), '-af',
        base + f',loudnorm=I={args.lufs:g}:TP=-1.5:LRA=11:print_format=json',
        '-vn', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    measured, _ = json.JSONDecoder().raw_decode(analysis.stderr[analysis.stderr.rfind('{'):].strip())
    normalize = (f'loudnorm=I={args.lufs:g}:TP=-1.5:LRA=11:measured_I={measured["input_i"]}'
        f':measured_TP={measured["input_tp"]}:measured_LRA={measured["input_lra"]}'
        f':measured_thresh={measured["input_thresh"]}:offset={measured["target_offset"]}'
        ':linear=true:print_format=json')
    command = ['ffmpeg', '-hide_banner', '-nostats', '-n', '-i', str(video), '-i', str(audio),
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-af', base + ',' + normalize,
        '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-ac', '2', '-t', f'{duration:g}',
        '-map_metadata', '0', '-metadata:s:a:0', 'title=' + (args.title or audio.stem),
        '-disposition:a:0', 'default', '-movflags', '+faststart', str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    (output.parent / 'audio-encode.log').write_text(result.stderr)
    target = probe(output)
    encoded_video = next(s for s in target['streams'] if s['codec_type'] == 'video')
    encoded_audio = next(s for s in target['streams'] if s['codec_type'] == 'audio')
    original = next(s for s in source_video['streams'] if s['codec_type'] == 'video')
    assert encoded_audio['codec_name'] == 'aac' and encoded_audio['channels'] == 2
    assert abs(float(target['format']['duration']) - duration) < .05
    assert abs(float(encoded_audio['duration']) - duration) < .05
    for key in ['width', 'height', 'r_frame_rate', 'nb_frames']:
        assert encoded_video[key] == original[key], key
    before, after = video_hash(video), video_hash(output)
    assert before == after, 'Video bitstream changed'
    receipt = dict(video=video.name, video_sha256=sha(video), audio=audio.name,
        audio_sha256=sha(audio), audio_source_duration=float(source_audio['format']['duration']),
        duration=duration, target_lufs=args.lufs, true_peak_limit=-1.5,
        fade_in_seconds=args.fade_in, fade_out_seconds=args.fade_out,
        silence_padding_seconds=max(0, duration-float(source_audio['format']['duration'])),
        measured_first_pass=measured, audio_codec='aac', audio_bitrate=256000,
        sample_rate=48000, channels=2, video_stream_copy=True,
        video_bitstream_hash=after, video_bitstream_identical=True,
        output=output.name, output_sha256=sha(output), audio_user_provided=True,
        audio_included_in_source_package=False)
    output.with_suffix('.audio-recipe.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print('AUDIO_ADDED_VIDEO_BITSTREAM_IDENTICAL', output, flush=True)


if __name__ == '__main__':
    main()
