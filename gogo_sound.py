"""Play the Go Go sound bank and turn battle effects into one-shot cues."""

from pathlib import Path
from time import monotonic

from panda3d.core import AudioSound, Filename

from arena import ASSASSIN, STEP


ASSETS = Path(__file__).resolve().parent / "assets" / "sounds"
# Hero order matches the roster. The cues describe the impact and the special ability.
ATTACKS = ("tank_hit", "magic_hit", "arrow_hit", "blade_hit", "fighter_hit")
ABILITIES = ("ice_dome", "snowfire", "frost_volley", "night_slip", "tidal_rush")
# Each cue has a gain, minimum retrigger interval, and mixing priority.
CUES = {
    "open": (.36, .07, 2), "back": (.32, .07, 2), "select": (.30, .05, 2),
    "denied": (.40, .16, 2), "buy": (.47, .08, 2), "sell": (.44, .08, 2),
    "place": (.42, .08, 2), "upgrade": (.48, .12, 3), "ready": (.43, .10, 2),
    "camera": (.24, .10, 1), "draft": (.43, .18, 3), "countdown": (.42, .18, 3),
    "fight": (.63, .25, 4), "round_win": (.54, .30, 4), "round_loss": (.50, .30, 4),
    "victory": (.63, .30, 4), "defeat": (.57, .30, 4), "draw": (.50, .30, 4),
    "tank_hit": (.29, .075, 1), "magic_hit": (.26, .075, 1), "arrow_hit": (.26, .075, 1),
    "blade_hit": (.25, .075, 1), "fighter_hit": (.29, .075, 1),
    "ice_dome": (.44, .10, 3), "snowfire": (.53, .10, 3), "frost_volley": (.43, .10, 3),
    "night_slip": (.46, .10, 3), "tidal_rush": (.49, .10, 3),
    "block": (.23, .09, 1), "skate": (.14, .14, 1), "knockout": (.43, .10, 3),
}


class GoGoSounds:
    def __init__(self, loader, enabled):
        self.loader = loader
        self.bank = {}
        self.active = []
        self.triggered = {}
        self.wind = None
        self.in_arena = False
        self.enabled = False
        self.set_enabled(enabled)

    def load(self, cue):
        return self.loader.loadSfx(Filename.fromOsSpecific(str(ASSETS / f"{cue}.wav")))

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            if self.wind is None:
                self.wind = self.load("wind")
                self.wind.setLoop(True)
            self.set_scene(self.in_arena)
            self.wind.play()
        else:
            self.stop_effects()
            if self.wind is not None:
                self.wind.stop()

    def set_scene(self, in_arena):
        self.in_arena = in_arena
        if self.wind is not None:
            self.wind.setVolume(.095 if in_arena else .065)

    def stop_effects(self):
        for _, voice in self.active:
            voice.stop()
        self.active.clear()
        self.triggered.clear()

    def close(self):
        self.set_enabled(False)
        self.bank.clear()
        self.wind = None

    def play(self, cue, gain=1.):
        if not self.enabled:
            return
        volume, interval, priority = CUES[cue]
        now = monotonic()
        if now-self.triggered.get(cue, -float("inf")) < interval:
            return
        voices = self.bank.setdefault(cue, [])
        voice = next((sound for sound in voices if sound.status() != AudioSound.PLAYING), None)
        if voice is None and len(voices) >= 2:
            return
        self.active = [(rank, voice) for rank, voice in self.active if voice.status() == AudioSound.PLAYING]
        if len(self.active) >= 8:
            quietest = min(self.active, key=lambda item: item[0])
            if quietest[0] >= priority:
                return
            quietest[1].stop()
            self.active.remove(quietest)

        if voice is None:
            voice = self.load(cue)
            voices.append(voice)
        voice.setVolume(volume*gain)
        voice.play()
        self.triggered[cue] = now
        self.active.append((priority, voice))

    def step_battle(self, match):
        if not self.enabled or match.phase != "fight":
            match.step()
            return

        old_effects = {id(effect): effect for effect in match.effects}
        actors = [(unit, unit.shield, unit.glide_left) for unit in match.fighters if unit.hp > 0]
        match.step()

        # An area spell can spawn one effect per target. Give the cast one voice.
        casts = set()
        for effect in match.effects:
            if id(effect) in old_effects:
                continue
            if not effect.spell:
                self.play(ATTACKS[effect.hero])
                continue
            if effect.hero == ASSASSIN and effect.blink_actor is None:
                continue
            cast = effect.side, effect.hero, effect.origin
            if cast not in casts:
                self.play(ABILITIES[effect.hero])
                casts.add(cast)

        for unit, shield, glide in actors:
            if unit.hp <= 0:
                self.play("knockout")
                continue
            if shield-unit.shield > STEP*8+.01:
                self.play("block")
            if glide <= STEP < unit.glide_left:
                self.play("skate", 1. if unit.knocked_back else .64)
