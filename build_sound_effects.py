"""Render the original layered sound effects shipped with Go Go 3D."""

from array import array
from dataclasses import dataclass
from math import exp, sin, tau
from random import Random
import wave

from gogo_sound import ASSETS, CUES


RATE = 32000
GLASS = ((1., 1.), (2.76, .24), (5.41, .10))
METAL = ((1., 1.), (1.48, .42), (2.31, .19), (4.7, .06))
HORN = ((1., 1.), (2., .32), (3., .14), (5., .055))


@dataclass(frozen=True)
class Tone:
    start: float
    length: float
    hz: float
    gain: float
    end: float | None = None
    attack: float = .006
    falloff: float = 2.8
    partials: tuple = ((1., 1.),)


@dataclass(frozen=True)
class Noise:
    start: float
    length: float
    low: float
    high: float
    gain: float
    attack: float = .005
    falloff: float = 2.4


def notes(frequencies, spacing, *, start=0., length=.32, gain=.48, partials=GLASS):
    return tuple(Tone(start+i*spacing, length, hz, gain, partials=partials)
                 for i, hz in enumerate(frequencies))


def impact(start, hz, gain, length=.25):
    return (Tone(start, length, hz, gain, end=hz*.42, partials=HORN, falloff=3.6),
            Noise(start+.004, length*.76, 75, 1500, gain*.72, falloff=3.5))


RECIPES = {
    "open": (Noise(0, .17, 850, 4800, .36, attack=.023), *notes((523, 784), .048, length=.20)),
    "back": (Tone(0, .16, 730, .68, end=330, partials=GLASS), Noise(0, .14, 560, 3000, .28)),
    "select": (Noise(0, .094, 440, 4200, .55, attack=.012), Tone(.015, .11, 625, .63, partials=GLASS)),
    "denied": (Tone(0, .19, 294, .72, end=214, partials=HORN), Tone(.09, .20, 196, .38)),
    "buy": (*impact(0, 148, .40, .12), *notes((784, 1047, 1397), .043, start=.027, length=.20)),
    "sell": (Noise(0, .15, 600, 4500, .31), *notes((1175, 880, 659), .057, length=.21, partials=METAL)),
    "place": (*impact(.022, 125, .64, .18), Noise(0, .15, 450, 3900, .58, attack=.030)),
    "upgrade": (*notes((392, 587, 784, 1175), .058, length=.40),
                Tone(.20, .48, 196, .27, partials=HORN, attack=.060), Noise(.09, .40, 1800, 7600, .32, attack=.13)),
    "ready": (*impact(.015, 162, .65, .18), Tone(.026, .27, 622, .52, partials=METAL),
              Tone(.093, .29, 831, .41, partials=GLASS)),
    "camera": (Noise(0, .21, 400, 3600, .61, attack=.060), Tone(.024, .19, 189, .24, end=275)),
    "draft": (*notes((294, 440, 587), .075, length=.42), Tone(.07, .51, 147, .24, partials=HORN, attack=.042)),
    "countdown": (Tone(0, .12, 932, .72, partials=GLASS, falloff=4.5), Noise(0, .055, 800, 3200, .24)),
    "fight": (*impact(0, 126, .87, .44), *impact(.135, 91, .68, .39),
              Tone(.035, .60, 147, .46, partials=HORN, attack=.070),
              Tone(.148, .51, 220, .35, partials=HORN, attack=.063),
              Tone(.24, .42, 440, .29, partials=METAL), Noise(0, .52, 240, 3700, .45, attack=.091)),
    "round_win": (*notes((392, 494, 587, 784), .105, length=.43), Tone(.31, .58, 196, .23, partials=HORN)),
    "round_loss": (*notes((392, 349, 294), .15, length=.49, partials=HORN), Tone(.27, .54, 147, .30)),
    "victory": (*impact(0, 111, .63, .35), *notes((392, 494, 587, 784, 988), .115, length=.54),
                *notes((196, 294, 392), .15, start=.34, length=.76, gain=.36, partials=HORN)),
    "defeat": (*impact(0, 98, .52, .35), *notes((330, 294, 220, 147), .17, length=.62, partials=HORN),
               Tone(.43, .59, 165, .30, partials=GLASS, attack=.07)),
    "draw": (*notes((440, 349, 440), .125, length=.42), Tone(.13, .60, 175, .23, partials=HORN, attack=.06)),
    "tank_hit": (*impact(0, 108, .78, .26), Noise(.007, .17, 530, 4100, .50),
                 Tone(.012, .19, 436, .23, partials=METAL)),
    "magic_hit": (Tone(0, .21, 1080, .61, end=590, partials=GLASS),
                  Noise(.015, .19, 950, 5600, .58, attack=.026), Tone(.04, .13, 170, .34, end=90)),
    "arrow_hit": (Tone(0, .14, 1230, .59, end=420, partials=METAL, falloff=4.2),
                  Noise(.035, .13, 790, 6500, .62, attack=.003), Tone(.052, .11, 246, .35)),
    "blade_hit": (Noise(0, .18, 610, 6800, .73, attack=.023),
                  Tone(.031, .16, 780, .50, end=407, partials=METAL), Tone(.060, .15, 137, .30, end=71)),
    "fighter_hit": (*impact(.021, 127, .71, .22), Noise(0, .15, 490, 4100, .54, attack=.021),
                    Tone(.028, .15, 386, .29, partials=METAL)),
    "ice_dome": (Tone(0, .54, 191, .53, end=309, partials=HORN, attack=.046),
                 Noise(.024, .56, 500, 3900, .52, attack=.075),
                 *notes((659, 988, 1319), .049, start=.095, length=.49, gain=.33)),
    "snowfire": (*impact(.078, 126, .81, .50), Noise(0, .63, 160, 6400, .78, attack=.077),
                 Tone(.07, .52, 305, .47, end=88, partials=HORN),
                 *notes((920, 1330, 1560), .063, start=.15, length=.24, gain=.18)),
    "frost_volley": (Noise(0, .16, 850, 7100, .65, attack=.016), Tone(0, .20, 1568, .61, end=640, partials=GLASS),
                     Noise(.112, .24, 620, 6300, .56), *notes((1175, 1568, 2093), .031, start=.11, length=.33, gain=.27)),
    "night_slip": (Noise(0, .35, 200, 2400, .54, attack=.10), Tone(0, .31, 146, .50, end=550, attack=.076),
                   Tone(.202, .36, 720, .58, end=240, partials=METAL),
                   *impact(.218, 112, .67, .34), Tone(.225, .44, 1046, .30, partials=GLASS)),
    "tidal_rush": (Noise(0, .44, 180, 4800, .73, attack=.058), Tone(0, .24, 140, .42, end=260, attack=.08),
                   *impact(.105, 135, .83, .37), Tone(.20, .40, 492, .30, partials=METAL)),
    "block": (Tone(0, .22, 855, .72, partials=METAL), Noise(0, .13, 420, 3900, .40)),
    "skate": (Noise(0, .22, 210, 3500, .55, attack=.045), Noise(.07, .18, 850, 5200, .18, attack=.036)),
    "knockout": (*impact(.092, 118, .71, .33), Noise(.045, .40, 225, 4500, .52, attack=.045),
                 Tone(0, .38, 448, .53, end=196, partials=HORN, falloff=2.2),
                 Tone(.17, .41, 523, .23, partials=GLASS)),
}


def render(cue, layers):
    rng = Random(cue)
    mix = [0.] * round(RATE*max(layer.start+layer.length for layer in layers))
    for layer in layers:
        start = round(RATE*layer.start)
        count = min(len(mix)-start, round(RATE*layer.length))
        if isinstance(layer, Tone):
            sweep = ((layer.end or layer.hz)-layer.hz)/(2*layer.length)
        else:
            slow = 1-exp(-tau*layer.low/RATE)
            fast = 1-exp(-tau*layer.high/RATE)
            lower = upper = 0.
        for index in range(count):
            t = index/RATE
            envelope = min(1., t/layer.attack)*(1-index/count)**layer.falloff
            if isinstance(layer, Tone):
                phase = tau*t*(layer.hz+sweep*t)
                sample = sum(gain*sin(phase*ratio) for ratio, gain in layer.partials)
            else:
                white = rng.uniform(-1., 1.)
                lower += slow*(white-lower)
                upper += fast*(white-upper)
                sample = upper-lower
            mix[start+index] += layer.gain*envelope*sample
    return mix


def wind_loop():
    rng = Random(9142)
    source = [rng.uniform(-1., 1.) for _ in range(6*RATE)]
    low = upper = 0.
    output = [0.] * len(source)
    for _ in range(2):
        for i, white in enumerate(source):
            low += .013*(white-low)
            upper += .10*(white-upper)
            phase = tau*i/len(source)
            gust = .56+.23*sin(phase*2+.5)+.13*sin(phase*3)
            output[i] = gust*(upper-low)+.075*sin(phase*492+.45*sin(phase*2))
    return output


def write_cue(name, samples, peak=.72):
    scale = 32767*peak/max(abs(value) for value in samples)
    pcm = array("h", (round(sample*scale) for sample in samples))
    with wave.open(str(ASSETS / f"{name}.wav"), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    if RECIPES.keys() != CUES.keys():
        raise ValueError("Sound recipes do not match the game cue list.")
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, layers in RECIPES.items():
        write_cue(name, render(name, layers))
    write_cue("wind", wind_loop(), peak=.59)
