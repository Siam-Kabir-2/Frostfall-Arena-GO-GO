"""Card battle HUD using the Coral and Azure art kit."""

from pathlib import Path

from panda3d.core import CardMaker, Filename, TextNode, Texture, TransparencyAttrib

from arena import COUNTDOWN, HAND, MAX_ROUNDS, ROSTER
from gogo_runtime.geometry import GOLD, TEAM, TOP, ease
from gogo_runtime.hud import Button, FEED, HudLayout, INK, MUTED, NIGHT
from gogo_stage import hero_tint, world
from gogo_ui_kit import (
    ArenaKit, BATTLE_FIELDS, BATTLE_REGION, CORAL_WIDTH, CREST_WIDTH,
    FRAME_HEIGHT, FRAME_WIDTH, HEADER_BUTTON_REGIONS, HELP_PANEL, HOME_REGIONS, HOME_TOOL_REGIONS,
    SCOREBOARD_REGION, SETTINGS_PANEL, SETTINGS_ROWS, TITLE_REGION,
    fit_region, region_aspect,
)
from planners import DRAFT_PLANNERS
from sprites import STANDING_HEIGHT

CENTER = TextNode.ACenter
RIGHT = TextNode.ARight
ICE_BLUE = (.41, .91, 1, 1)
SIDE_ART = ("coral", "azure")
CARD_ROOT = Path(__file__).resolve().parent / "assets" / "cards"


def ui_scale(width, height):
    return min(1.32, height/900, width/(850 if width/height < 1.36 else 1140))


def match_header_layout(width, scale):
    stacked = width < 1030*scale
    room = width-(22 if stacked else 576)*scale
    score_w = min(660*scale, room)
    score_h = score_w/region_aspect(SCOREBOARD_REGION)
    score = ((width-score_w)/2, 5*scale, score_w, score_h)
    score_bottom = score[1]+score_h

    margin = 22*scale
    badge_w = (165 if stacked else 253)*scale
    badge_h = badge_w/region_aspect(TITLE_REGION)
    badge_y = score_bottom+3*scale if stacked else 9*scale
    badge = (margin, badge_y, badge_w, badge_h)

    button_h = (75 if stacked else 77)*scale
    button_y = badge_y+(badge_h-button_h)/2 if stacked else 21*scale
    gap = 9*scale
    button_widths = [button_h*region_aspect(region) for region in HEADER_BUTTON_REGIONS.values()]
    left = width-margin-sum(button_widths)-gap*(len(button_widths)-1)
    buttons = []
    for button_w in button_widths:
        buttons.append((left, button_y, button_w, button_h))
        left += button_w+gap
    bottom = max(score_bottom, badge_y+badge_h, button_y+button_h)+9*scale
    return score, badge, buttons, bottom


def dock_layout(width, height, scale):
    span = min(width-16*scale, 1612*scale)
    if width < 1150*scale:
        left = (width-span)/2
        hand_w = (span-4*scale)/2
        dock_h = hand_w*FRAME_HEIGHT/CORAL_WIDTH
        floor = height-dock_h-9*scale
        badge_w = min(432*scale, span)
        status = ((width-badge_w)/2, floor-47*scale, badge_w, 43*scale)
        return (left, floor, hand_w, dock_h), (width-left-hand_w, floor, hand_w, dock_h), status

    factor = min(span/FRAME_WIDTH, 203*scale/FRAME_HEIGHT)
    dock_h = FRAME_HEIGHT*factor
    floor = height-dock_h-9*scale
    left = (width-FRAME_WIDTH*factor)/2
    coral_w, badge_w = CORAL_WIDTH*factor, CREST_WIDTH*factor
    azure_w = (FRAME_WIDTH-CORAL_WIDTH-CREST_WIDTH)*factor
    return ((left, floor, coral_w, dock_h),
            (left+coral_w+badge_w, floor, azure_w, dock_h),
            (left+coral_w, floor, badge_w, dock_h))


class GoGoHUD(HudLayout):
    def __init__(self, base, fonts):
        super().__init__(base, fonts)
        self.card_slots = []
        self.kit = ArenaKit(base.loader, self)
        self.label_measure = TextNode("HUD label measurement")
        self.label_measure.setFont(fonts["heavy"])
        self.portraits = {}
        for side in (0, 1):
            for hero in range(len(ROSTER)):
                path = Filename.fromOsSpecific(str(CARD_ROOT / f"{side}-{hero}.png"))
                texture = base.loader.loadTexture(path)
                if texture:
                    texture.setMinfilter(Texture.FTLinearMipmapLinear)
                    texture.setMagfilter(Texture.FTLinear)
                self.portraits[side, hero] = texture

    def portrait(self, side, hero, x, y, w, h, fade=False):
        texture = self.portraits[side, hero]
        if not texture:
            return
        scale = min(w/texture.getXSize(), h/texture.getYSize())
        art_w, art_h = texture.getXSize()*scale, texture.getYSize()*scale
        x, y = x+(w-art_w)/2, y+(h-art_h)/2
        maker = CardMaker("Hero portrait")
        maker.setFrame(x, x+art_w, -y-art_h, -y)
        node = self.layer.attachNewNode(maker.generate())
        node.setTexture(texture)
        node.setBin("fixed", self.position)
        node.setTransparency(TransparencyAttrib.MAlpha)
        self.position += 1
        if fade:
            node.setColorScale(.62, .69, .76, 1)

    def card_at(self, mouse):
        px, py = mouse
        for side, kind, slot, (x, y, w, h) in self.card_slots:
            if x <= px < x+w and y <= py < y+h:
                return side, kind, slot
        return None

    def home(self, game):
        if self.compact:
            s = min(self.h/476, self.w/400)
            x, y = (self.w-248*s)/2, self.h-280*s
        else:
            s = min(self.h/394, self.w/690)
            x, y = 11*s, (self.h-394*s)*.35+88*s

        def centered(name, top, width):
            w = width*s
            area = (x+(248*s-w)/2, y+top*s, w, w/region_aspect(HOME_REGIONS[name]))
            self.kit.home_sprite(name, area)

        self.kit.home_sprite("panel", (x, y, 248*s, 264*s))
        centered("logo", -69, 226)
        centered("heading", 27, 170)
        for index, mode in enumerate(("local", "cpu", "showdown")):
            area = (x+16*s, y+(66+57*index)*s, 216*s, 55*s)
            self.home_button(mode, area, lambda mode=mode: game.mode_key(mode))

        toolbar = (("help", lambda: game.open_modal("help")), ("sound", game.toggle_sound),
                   ("settings", lambda: game.open_modal("settings")), ("exit", game.userExit))
        height = 26*s
        right = self.w-9*s
        for name, action in reversed(toolbar):
            width = height*region_aspect(HOME_TOOL_REGIONS[name])
            area = (right-width, 9*s, width, height)
            art = self.home_button(name, area, action)
            if name == "sound" and not game.sound:
                art.setColor(.53, .67, .84, 1)
                left, top, w, h = area
                self.geometry("Muted sound slash", tuple((left+px*w, top+py*h) for px, py in
                              ((.28, .25), (.35, .20), (.73, .68), (.66, .73))), (1, .74, .62, 1))
            right -= width+4*s

    def home_button(self, name, area, action):
        art = self.kit.home_sprite(name, area)
        self.buttons.append(Button(area, action, art))
        return art

    def ai_setup(self, game, mode):
        s = self.s
        human_match = mode == "cpu"
        title = "Human vs AI" if human_match else "AI vs AI"
        subtitle = ("You play Coral. Choose how Azure drafts its lineup." if human_match else
                    "Choose a draft algorithm for each team.")
        x, y, w, h = self.dialog(title, subtitle, 760, 341 if human_match else 502)
        gap = 12*s
        card_width = (w-64*s-gap*(len(DRAFT_PLANNERS)-1))/len(DRAFT_PLANNERS)
        sides = (1,) if human_match else (0, 1)
        for row, side in enumerate(sides):
            top = y+(115+139*row)*s
            color = TEAM[side]
            self.kit.draw(f"{SIDE_ART[side]}_crest", (x+32*s, top, 25*s, 25*s))
            self.text("AZURE OPPONENT" if human_match else SIDE_ART[side].upper(),
                      x+66*s, top+20*s, 20, color, "label")
            selected = game.ai_planner(side, mode=mode)
            for index, (key, planner) in enumerate(DRAFT_PLANNERS.items()):
                bounds = (x+32*s+index*(card_width+gap), top+34*s, card_width, 102*s)
                self.algorithm_card(planner, bounds, color, planner is selected,
                                    lambda side=side, key=key: game.select_ai(mode, side, key))
        if not human_match:
            self.text("Both teams draft from the same public deck.", x+32*s, y+h-88*s, 16, FEED)
        self.button("Back", (x+32*s, y+h-72*s, 126*s, 46*s), game.close_modal)
        self.button("Start match", (x+w-229*s, y+h-72*s, 197*s, 46*s),
                    game.confirm, primary=True, arrow=True, size=20)

    def algorithm_card(self, planner, bounds, accent, selected, action):
        x, y, w, h = bounds
        s = self.s
        frame = self.plate(x, y, w, h, accent, strong=selected)
        self.track_ice_button(bounds, action, frame)
        self.text(planner.label, x+16*s, y+37*s, 30, INK, "heavy")
        self.paragraph(planner.description, x+16*s, y+63*s, w-32*s, 16, FEED, 2)
        mark = (*accent[:3], 1) if selected else (.36, .51, .64, 1)
        self.shape(x+w-27*s, y+20*s, 11*s, 11*s, mark, 6*s)
        if selected:
            self.text("SELECTED", x+w-32*s, y+30*s, 11, accent, "label", RIGHT)
        else:
            self.shape(x+w-25*s, y+22*s, 7*s, 7*s, (.05, .11, .20, 1), 4*s)

    def artwork_dialog(self, name, panel):
        self.buttons.clear()
        self.blocked = [(0, 0, self.w, self.h)]
        self.shape(0, 0, self.w, self.h, (.009, .022, .042, .66))
        aspect = region_aspect(panel)
        w = min(self.w*.94, self.h*.91*aspect)
        h = w/aspect
        bounds = ((self.w-w)/2, (self.h-h)/2, w, h)
        self.kit.dialog_panel(name, bounds, panel)
        return bounds

    def artwork_button(self, name, panel_name, bounds, panel, pixels, action):
        area = fit_region(bounds, panel, pixels)
        art = self.kit.dialog_detail(panel_name, name, area, pixels)
        self.buttons.append(Button(area, action, art))

    def help(self, game):
        bounds = self.artwork_dialog("help", HELP_PANEL)
        shortcuts = (("cpu", (219, 701, 541, 809)), ("local", (563, 700, 943, 809)),
                     ("showdown", (966, 700, 1235, 809)))
        if game.mode is None:
            for mode, pixels in shortcuts:
                self.artwork_button(mode, "help", bounds, HELP_PANEL, pixels,
                                    lambda mode=mode: game.mode_key(mode))
        self.artwork_button("help-back", "help", bounds, HELP_PANEL, (488, 830, 957, 988), game.close_modal)

    def settings(self, game):
        bounds = self.artwork_dialog("settings", SETTINGS_PANEL)
        items = (("Sound effects", game.sound, game.toggle_sound),
                 ("Fullscreen", game.fullscreen, game.toggle_fullscreen))
        for (name, on, action), pixels in zip(items, SETTINGS_ROWS):
            area = fit_region(bounds, SETTINGS_PANEL, pixels)
            art = self.kit.setting_switch(name, area, on)
            x, y, w, h = area
            # The enlarged selected side overlaps the center of the segmented sprite.
            target = (x+w*.57, y, w*.43, h) if on else (x, y, w*.43, h)
            self.buttons.append(Button(target, action, art))
        self.artwork_button("settings-back", "settings", bounds, SETTINGS_PANEL, (396, 754, 1051, 987),
                            game.close_modal)

    def header(self, game):
        scoreboard, badge, buttons, _ = match_header_layout(self.w, self.s)
        self.scoreboard(game, scoreboard)
        self.kit.title_badge(badge)
        self.blocked.append(badge)

        actions = (game.toggle_view, game.home, lambda: game.open_modal("pause"))
        for name, area, action in zip(HEADER_BUTTON_REGIONS, buttons, actions):
            art = self.kit.header_button(name, area)
            if name == "view" and game.overhead:
                art.setColor(.70, .98, 1, 1)
            self.buttons.append(Button(area, action, art))

    def scoreboard(self, game, bounds):
        x, y, w, h = bounds
        l, t, r, b = SCOREBOARD_REGION
        sx, sy = w/(r-l), h/(b-t)

        def place(left, top, right, bottom):
            return x+(left-l)*sx, y+(top-t)*sy, (right-left)*sx, (bottom-top)*sy

        match = game.match
        phase = match.phase
        self.kit.scoreboard(bounds)
        self.blocked.extend((place(53, 65, 2122, 429), place(476, 439, 1696, 660)))
        self.fit_label(f"ROUND {match.round_number}/{MAX_ROUNDS}", place(915, 207, 1256, 336), 26)
        for side, team in enumerate(match.sides):
            name_x, score_x = (1470, 1318) if side else (487, 738)
            self.fit_label(game.team_name(side).upper(), place(name_x, 167, name_x+225, 295), 35)
            self.fit_label(str(match.round_wins[side]), place(score_x, 169, score_x+122, 345), 54)
            if phase != "prep":
                standing = sum(unit.side == side and unit.hp > 0 for unit in match.fighters)
                detail = f"{standing}/{len(team.field)} STANDING"
            elif team.ready:
                detail = "READY"
            elif team.to_deploy:
                detail = f"{team.to_deploy} TO PLACE"
            else:
                detail = f"{len(team.field)}/5 DEPLOYED" if game.human(side) else "PLANNING"
            if game.mode == "showdown":
                if not team.to_deploy:
                    detail = detail.split()[0]
                detail = f"{game.ai_planner(side).label.upper()} · {detail}"
            self.fit_label(detail, place(name_x-15, 289, name_x+240, 352), 16, color=INK)

        if phase == "prep":
            title = ("AWAITING LINEUPS" if match.seconds_left == 0 else
                     "REDEPLOY PHASE" if any(team.to_deploy for team in match.sides) else "SETUP PHASE")
        else:
            title = {"countdown": "BATTLE STARTING", "fight": "TIME LEFT",
                     "round_end": "ROUND COMPLETE", "end": "MATCH COMPLETE"}[phase]
        if phase == "fight":
            remaining = match.seconds_left
            self.fit_label(title, place(675, 472, 1146, 597), 28)
            self.fit_label(f"{remaining//60:02}:{remaining%60:02}", place(1160, 466, 1508, 605), 40, color=ICE_BLUE)
        else:
            self.fit_label(title, place(610, 471, 1562, 598), 29)

    def fit_label(self, label, area, size, *, color=INK, align=CENTER):
        x, y, w, h = area
        size = min(size, h/self.s*.72)
        text_w = max(.1, self.label_measure.calcWidth(label))*self.s
        size = min(size, (w-4*self.s)/text_w)
        label_x = x+w/2 if align == CENTER else x+3*self.s
        node = self.text(label, label_x, y+h/2+size*self.s*.30, size, color, "heavy", align)
        node.node().setShadow(.048, .075)
        return node

    def dock_button(self, title, bounds, action=None):
        x, y, w, h = bounds
        disabled = action is None
        overlay = self.shape(x+2, y+2, w-4, h-4, (.025, .042, .09, .60) if disabled else (1, 1, 1, .24),
                             h*.24)
        label = self.fit_label(title.upper(), (x+w*.28, y, w*.70, h), 22, color=MUTED if disabled else INK)
        if not disabled:
            overlay.hide()
            self.buttons.append(Button(bounds, action, label, overlay))

    def card_cost(self, cost, bounds):
        x, y, w, h = bounds
        s = self.s
        coin = min(19*s, h*.95)
        left = x+w/2-coin
        self.kit.draw("shell", (left, y+(h-coin)/2, coin, coin))
        size = min(21, h/s)
        self.text(cost, left+coin+2*s, y+h/2+size*s*.29, size, GOLD, "heavy")

    def hero_card(self, side, bounds, hero_id, *, rank=None, selected=False, fade=False, health=None):
        x, y, w, h = bounds
        s = self.s
        if selected:
            self.kit.draw(f"{SIDE_ART[side]}_focus", (x-4*s, y-3*s, w+8*s, h+6*s))
        hero = ROSTER[hero_id]
        self.portrait(side, hero_id, x+w*.09, y+h*.06, w*.82, h*.54, fade)
        self.fit_label(hero.name, (x+w*.04, y+h*.59, w*.92, h*.22), 16, color=MUTED if fade else INK)
        if rank is not None:
            self.shape(x+w*.09, y+h*.07, w*.29, h*.20, NIGHT, 3*s)
            self.fit_label(f"R{rank}", (x+w*.09, y+h*.07, w*.29, h*.20), 12, color=GOLD)
        else:
            self.card_cost(hero.cost, (x, y+h*.78, w, h*.19))
        if health is not None:
            track_w = w*.76
            self.rounded(x+w*.12, y+h*.87, track_w, max(2*s, h*.052), NIGHT, 2*s)
            if health > 0:
                self.rounded(x+w*.12, y+h*.87, track_w*health, max(2*s, h*.052), TEAM[side], 2*s)

    def hand(self, game, side, x, y, w, h):
        team = game.match.sides[side]
        returning = team.to_deploy > 0
        private = game.mode == "cpu" and side == 1
        dock = self.kit.dock(side, (x, y, w, h))
        self.fit_label(game.team_name(side).upper(), dock.name, 32, align=TextNode.ALeft)
        self.fit_label(f"{team.shells} SHELLS", dock.shells, 22, color=GOLD)
        caption = "LINEUP" if private else "REDEPLOY" if returning else f"HAND ({HAND} CARDS)"
        self.kit.draw("azure_tag", dock.hand)
        self.fit_label(caption, dock.hand, 14)

        if private:
            for bounds, recruit in zip(dock.slots, team.field.values()):
                self.hero_card(side, bounds, recruit.hero, rank=recruit.rank)
            self.dock_button(game.ai_planner(side).label, dock.upgrade)
            self.dock_button("Locked" if team.ready else "Planning", dock.ready)
            return

        for slot, bounds in enumerate(dock.slots):
            if returning:
                if slot >= len(team.returning) or team.returning[slot] is None:
                    continue
                recruit = team.returning[slot]
                hero_id, kind, rank = recruit.hero, "return", recruit.rank
            elif slot == HAND:
                self.fit_label("NEXT", dock.next_label, 13)
                self.hero_card(side, bounds, team.next_card)
                break
            else:
                hero_id, kind, rank = team.hand[slot], "card", None
            self.hero_card(side, bounds, hero_id, rank=rank,
                           selected=game.selected == (side, kind, slot),
                           fade=not returning and team.shells < ROSTER[hero_id].cost)
            self.card_slots.append((side, kind, slot, bounds))

        human = game.human(side)
        allowed = human and any(game.match.can_upgrade(side, cell) for cell in team.field)
        upgrading = game.selected == (side, "upgrade", None)
        upgrade = "Pick unit" if upgrading else f"Upgrade {team.upgrades}"
        ready = f"{team.to_deploy} to place" if returning else (
            "Unlock" if team.ready and human else "Locked" if team.ready else "Ready" if human else "Planning")
        self.dock_button(upgrade, dock.upgrade, (lambda: game.select_upgrade(side)) if allowed else None)
        self.dock_button(ready, dock.ready, (lambda: game.ready(side)) if human and not returning else None)

    def battle_cards(self, game, side, bounds):
        name, counter, slots = BATTLE_FIELDS[side]
        self.fit_label(game.team_name(side).upper(), fit_region(bounds, BATTLE_REGION, name), 26)
        team = game.match.sides[side]
        fighters = [unit for unit in game.match.fighters if unit.side == side]
        standing = sum(unit.hp > 0 for unit in fighters)
        self.fit_label(f"{standing}/{len(team.field)} STANDING", fit_region(bounds, BATTLE_REGION, counter), 19)
        for (left, right), unit in zip(slots, fighters):
            card = fit_region(bounds, BATTLE_REGION, (left, 318, right, 526))
            recruit = unit.recruit
            self.hero_card(side, card, recruit.hero, rank=recruit.rank,
                           fade=unit.hp <= 0, health=unit.hp/unit.maximum)

    def ai_effort(self, game):
        if game.mode != "showdown":
            return ""
        parts = []
        for side, decision in sorted(game.decisions.items()):
            planner = game.ai_planner(side)
            if planner.effort:
                parts.append(f"{game.team_name(side)} {decision.explored} {planner.effort}")
        return " · ".join(parts)

    def battle_footer(self, game, left, right):
        _, y, _, h = left
        l, t, r, b = BATTLE_REGION
        w = min(right[0]+right[2]-left[0], h*(r-l)/((b-t)*.82))
        bounds = ((self.w-w)/2, y, w, h)
        self.kit.battle_frame(bounds)
        self.blocked.append(bounds)
        for side in (0, 1):
            self.battle_cards(game, side, bounds)
        match = game.match
        note = {"countdown": "GET READY", "fight": "HP TIEBREAK",
                "round_end": "ROUND COMPLETE", "end": "MATCH COMPLETE"}[match.phase]
        if match.phase == "fight":
            note = self.ai_effort(game) or note
        self.fit_label(note, fit_region(bounds, BATTLE_REGION, (976, 534, 1197, 586)), 14)

    def units(self, game):
        s = self.s
        height = STANDING_HEIGHT-.05+.105*game.view_amount
        headroom = game.cam.getQuat(game.stage.root).getUp()*height
        for point, side, recruit, hp, shield in game.stage.labels:
            screen = game.project(point+headroom)
            if not screen:
                continue
            x, y = screen
            w = 48*s
            self.shape(x-w/2, y-8*s, w, 5*s, (.035, .092, .17, 1), 1.5*s)
            if hp > .001:
                self.shape(x-w/2+s, y-7*s, (w-2*s)*hp, 3*s, TEAM[side], s)
            if shield:
                self.shape(x-w/2+s, y-1*s, (w-2*s)*min(1., shield/100), 2*s, GOLD)
            self.text(f"{ROSTER[recruit.hero].name}  {recruit.rank}", x, y-12*s, 13, INK, "label", CENTER).node().setShadow(.07, .07)
        for effect in game.stage.blinks.values():
            if not .36 <= effect.blink_progress <= .93:
                continue
            screen = game.project(world(*effect.target, TOP+.06)+headroom)
            if screen:
                x, y = screen
                label = self.text("NIGHT SLIP", x, y-15*s, 15, hero_tint(effect.hero), "label", CENTER)
                label.node().setShadow(.09, .09)
        for point, rank, progress in game.stage.upgrade_labels:
            screen = game.project(point+headroom)
            if screen:
                x, y = screen
                alpha = min(1., progress*14, (1-progress)*3)
                lift = ease(progress)*23*s
                self.shape(x-33*s, y-43*s-lift, 66*s, 22*s, (.08, .055, .03, alpha*.92), 5*s)
                self.text(f"RANK {rank}", x, y-27*s-lift, 17, (*GOLD[:3], alpha), "heavy", CENTER)

    def battle_status(self, game, mouse):
        selected = game.selected
        hover = self.card_at(mouse)
        status = game.notice if game.notice_time else ""
        if not status and selected and selected[1] == "upgrade":
            status = "Choose a marked penguin to raise its rank by one."
        if not status and (hover or (selected and selected[1] in ("card", "return"))):
            side, kind, slot = hover or selected
            team = game.match.sides[side]
            if kind == "return":
                recruit = team.returning[slot]
                if recruit is not None:
                    hero = ROSTER[recruit.hero]
                    status = f"Place {hero.name}  /  Rank {recruit.rank}  /  {hero.position}"
            else:
                hero = ROSTER[team.hand[slot]]
                status = f"{hero.role}  /  {hero.position}  /  {hero.spell}"
        if not status and any(team.to_deploy for team in game.match.sides):
            status = "Place your returning penguins to build a new formation."
        if not status and game.match.seconds_left == 0:
            status = "Deploy at least one penguin on each side to begin."
        return status

    def battle(self, game, mouse):
        s = self.s
        self.units(game)
        self.header(game)
        phase = game.match.phase
        left, right, status_bounds = dock_layout(self.w, self.h, s)
        if phase != "prep":
            self.battle_footer(game, left, right)
            return
        compact = status_bounds[3] < 60*s
        if not compact:
            # Use one quad so the glow between the two docks and crest stays continuous.
            self.kit.draw("draft_frame", (left[0], left[1], right[0]+right[2]-left[0], left[3]))
        for side, bounds in enumerate((left, right)):
            self.blocked.append(bounds)
            if compact:
                self.kit.draw(f"{SIDE_ART[side]}_dock", bounds)
            self.hand(game, side, *bounds)

        self.phase_badge(game, mouse, status_bounds)

    def phase_badge(self, game, mouse, bounds):
        s = self.s
        x, y, w, h = bounds
        middle = x+w/2
        match = game.match
        seconds = match.seconds_left
        title = "REDEPLOY" if any(team.to_deploy for team in match.sides) else "SETUP"
        color = INK
        if seconds:
            title = f"DRAFT TIME  ·  {seconds}s"
            if seconds <= 5:
                color = GOLD
        elif seconds == 0:
            title = "AWAITING LINEUPS"
        status = self.battle_status(game, mouse)
        status = status or self.ai_effort(game)
        self.blocked.append(bounds)
        if h < 60*s:
            self.kit.draw("toolbar", bounds)
            self.kit.draw("blank_crest", (x+24*s, y+2*s, 28*s, 38*s))
            self.text(title, x+62*s, y+18*s, 15, color, "heavy")
            self.paragraph(status or "Drag cards onto your side.", x+62*s, y+32*s, w-92*s, 11, FEED, 1)
            return

        title_area = (x+w*.08, y+h*.605, w*.84, h*.19)
        self.fit_label(title, title_area, 35, color=color)
        if status:
            hint = (x, y+h*.80, w, h*.19)
            self.kit.draw("toolbar", hint)
            self.paragraph(status, middle, hint[1]+hint[3]*.36, w-20*s, 10, FEED, 2, align=CENTER)
        else:
            crest = min(22*s, h*.10)
            self.kit.draw("azure_crest", (middle-crest/2, y+h*.82, crest, crest))

    def match_dialog(self, width, height, accent):
        self.buttons.clear()
        self.blocked = [(0, 0, self.w, self.h)]
        self.shape(0, 0, self.w, self.h, (.008, .020, .044, .73))
        self.s = min(1.4, self.w/(width+56), self.h/(height+76))
        w, h = width*self.s, height*self.s
        bounds = ((self.w-w)/2, (self.h-h)/2, w, h)
        self.ice_panel(*bounds, accent=accent)
        return bounds

    def battle_countdown(self, match):
        number = match.seconds_left
        beat = match.time-(COUNTDOWN-number)
        pulse = 1+.16*(1-ease(min(1., beat*4)))
        s = self.s
        x, y = self.w/2, self.h*.47
        w, h = 255*s, 171*s
        self.ice_panel(x-w/2, y-h/2, w, h, accent=ICE_BLUE)
        self.text(f"ROUND {match.round_number}", x, y-47*s, 18, FEED, "label", CENTER)
        number_art = self.text(number, x, y+37*s, 101*pulse, INK, "heavy", CENTER)
        number_art.node().setShadow(.045, .055)
        for index in range(COUNTDOWN):
            color = ICE_BLUE if index < number else (.21, .44, .57, 1)
            self.shape(x+(index-1)*24*s-6*s, y+55*s, 12*s, 6*s, color, 3*s)

    def pause_menu(self, game):
        x, y, w, h = self.match_dialog(514, 306, ICE_BLUE)
        s = self.s
        center = x+w/2
        self.kit.draw("blank_crest", (center-39*s, y+14*s, 78*s, 72*s))
        for left in (-11, 3):
            self.shape(center+left*s, y+37*s, 8*s, 23*s, INK, 2*s)
        self.text("MATCH PAUSED", center, y+124*s, 46, INK, "heavy", CENTER)

        match = game.match
        phase = {"prep": "Draft phase", "countdown": "Battle countdown", "fight": "Battle phase",
                 "round_end": "Round complete"}[match.phase]
        detail = f"Round {match.round_number} of {MAX_ROUNDS}  ·  {phase}"
        self.text(detail, center, y+156*s, 19, FEED, "body", CENTER)
        self.shape(x+36*s, y+182*s, w-72*s, s, (.37, .74, .88, .45))

        self.button("Main menu", (x+34*s, y+203*s, 157*s, 53*s), game.home, size=18)
        self.button("Resume match", (x+205*s, y+203*s, w-239*s, 53*s), game.close_modal,
                    primary=True, arrow=True, size=21)
        self.text("Esc or P to resume", center, y+h-23*s, 15, FEED, "body", CENTER)

    def match_result(self, game):
        match = game.match
        final = match.phase == "end"
        winner = match.winner if final else match.round_winner
        accent = ICE_BLUE if winner == -1 else TEAM[winner]
        x, y, w, h = self.match_dialog(628, 377 if final else 408, accent)
        s = self.s
        center = x+w/2
        stage = "MATCH COMPLETE" if final else f"ROUND {match.round_number} COMPLETE"
        title = "DRAW" if winner == -1 else f"{SIDE_ART[winner].upper()} WINS"
        self.text(stage, center, y+45*s, 17, FEED, "label", CENTER)
        self.text(title, center, y+103*s, 63, accent, "heavy", CENTER).node().setShadow(.045, .07)
        self.text("FINAL SCORE" if final else "MATCH SCORE", center, y+143*s, 15, FEED, "label", CENTER)

        for side, wins in enumerate(match.round_wins):
            left = x+(35+side*285)*s
            self.plate(left, y+159*s, 273*s, 87*s, TEAM[side], strong=side == winner)
            self.kit.draw(f"{SIDE_ART[side]}_crest", (left+15*s, y+180*s, 41*s, 44*s))
            team_top = 211 if game.human(side) else 198
            self.text(SIDE_ART[side].upper(), left+68*s, y+team_top*s, 25, INK, "label")
            if not game.human(side):
                self.text(game.ai_planner(side).label, left+68*s, y+223*s, 16, FEED)
            self.text(wins, left+249*s, y+224*s, 57, TEAM[side], "heavy", RIGHT)

        if final:
            self.text(f"{match.round_number} of {MAX_ROUNDS} rounds played", center, y+281*s, 19, FEED,
                      "body", CENTER)
        else:
            self.text(match.reason, center, y+279*s, 20, INK, "label", CENTER)
            detail = ("Next round starts automatically" if game.mode == "showdown" else
                      f"{match.round_number+1} upgrades per team next round")
            self.text(detail, center, y+306*s, 17, FEED, "body", CENTER)

        self.button("Home", (x+35*s, y+h-72*s, 170*s, 52*s), game.home, size=18)
        self.button("Rematch" if final else "Next round", (x+219*s, y+h-72*s, w-254*s, 52*s),
                    game.rematch if final else game.next_round, primary=True, arrow=True, size=21)

    def overlay(self, game):
        phase = game.match.phase
        if game.modal == "help":
            self.help(game)
        elif game.modal in ("cpu_setup", "ai_setup"):
            self.ai_setup(game, "cpu" if game.modal == "cpu_setup" else "showdown")
        elif game.modal == "settings":
            self.settings(game)
        elif game.modal == "pause":
            self.pause_menu(game)
        elif game.mode is not None and phase == "countdown":
            self.battle_countdown(game.match)
        elif game.mode is not None and phase in ("round_end", "end"):
            self.match_result(game)

    def draw(self, game, width, height, mouse):
        self.begin(width, height)
        self.s = ui_scale(width, height)
        self.card_slots.clear()
        if game.mode is None:
            self.home(game)
        else:
            self.battle(game, mouse)
        self.overlay(game)
