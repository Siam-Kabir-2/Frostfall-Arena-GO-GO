"""Create a silent home-menu loop from the original constant-frame-rate MP4."""

import argparse
import json
from fractions import Fraction
from pathlib import Path
from subprocess import run


def render_loop(source, output):
    probe = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=avg_frame_rate,nb_read_frames", "-of", "json", str(source),
    ], check=True, capture_output=True, text=True)
    stream, = json.loads(probe.stdout)["streams"]
    fps = Fraction(stream["avg_frame_rate"])
    end_frame = int(stream["nb_read_frames"])
    overlap = max(2, round(fps/3))
    if end_frame <= 2*overlap:
        raise ValueError("The video is too short to overlap its start and end.")

    tail_start = end_frame-overlap
    progress = f"(T*({fps})/{overlap-1})"
    weight = f"{progress}*{progress}*(3-2*{progress})"
    filters = (
        "[0:v:0]split=3[middle][tail][head];"
        f"[middle]trim=start_frame={overlap}:end_frame={tail_start},setpts=PTS-STARTPTS[main];"
        f"[tail]trim=start_frame={tail_start},setpts=PTS-STARTPTS[ending];"
        f"[head]trim=end_frame={overlap},setpts=PTS-STARTPTS[opening];"
        f"[ending][opening]blend=all_expr='round(A+(B-A)*({weight}))':shortest=1[dissolve];"
        # The final blended frame ends the opening segment. The loop starts on its next frame.
        f"[main][dissolve]concat=n=2:v=1:a=0,settb=expr={1/fps},setpts=N,setsar=1[loop]"
    )
    # Panda's bundled decoder repeats the first frame when seeking this clip as H.264.
    # Low-delay MPEG-2 keeps the frames advancing across each wrap.
    run([
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source),
        "-filter_complex", filters, "-map", "[loop]", "-an", "-c:v", "mpeg2video",
        "-q:v", "2", "-bf", "0", "-g", str(round(fps)), "-flags", "+low_delay",
        "-pix_fmt", "yuv420p", "-video_track_timescale", str(fps.numerator), "-movflags", "+faststart", str(output),
    ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original background video")
    parser.add_argument("output", type=Path, help="path to a new MP4 file")
    args = parser.parse_args()
    render_loop(args.source, args.output)
