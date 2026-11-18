import sys, tempfile, subprocess, os, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import shorts_clipper as core

core.ensure_tools_in_path()

# Create a 20-second test video with sine audio
tmp = Path(tempfile.mkdtemp())
test_vid = tmp / 'test.mp4'
subprocess.run([
    'ffmpeg', '-y', '-f', 'lavfi',
    '-i', 'color=c=blue:size=1920x1080:rate=30:duration=20',
    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=20',
    '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(test_vid)
], capture_output=True, check=True)
print('Test video created:', test_vid)

# Test duration
d = core.duration(test_vid)
print(f'Duration: {d:.1f}s')

# Test find_silences
silences = core.find_silences(test_vid)
print(f'Silences: {len(silences)}')

# Test plan_cuts
cuts = core.plan_cuts(d, 10, 3, silences)
print(f'Cuts: {cuts}')

# Test get_captions (sine audio = no speech, so whisper returns [])
captions = core.get_captions(test_vid, tmp, log_fn=print)
print(f'Captions: {len(captions)} bursts')

# Test virality score
v = core.calculate_virality_score(test_vid, 0, 10, d, silences, captions)
score = v['score']
tier = v['tier']
print(f'Virality: {score}/100 ({tier})')

# Test export all 4 templates
out_dir = tmp / 'out'
out_dir.mkdir()
errors = []
for i, (s, e) in enumerate(cuts[:2], 1):
    for fit in ['crop', 'blur', 'split', 'headline']:
        ass_path = out_dir / f'temp_{i}_{fit}.ass'
        ass_file = core.generate_ass(captions, s, e, 'tiktok_yellow', ass_path) if captions else None
        out_clip = out_dir / f'clip_{i}_{fit}.mp4'
        try:
            core.export(test_vid, s, e - s, out_clip, fit=fit, ass_file=ass_file)
            sz = out_clip.stat().st_size
            print(f'  OK: {out_clip.name} ({sz} bytes)')
        except Exception as ex:
            errors.append(f'{out_clip.name}: {ex}')
            print(f'  FAIL: {out_clip.name}: {ex}')

# Check virality_report JSON
report = [{'clip': f.name, 'size': f.stat().st_size} for f in out_dir.glob('*.mp4')]
(out_dir / 'virality_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('Report written:', (out_dir / 'virality_report.json').exists())

if errors:
    print(f'\nFAILED with {len(errors)} error(s):')
    for e in errors:
        print(' -', e)
    sys.exit(1)
else:
    print('\nALL TESTS PASSED')
