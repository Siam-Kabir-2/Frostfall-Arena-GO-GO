from importlib.util import find_spec
from unittest import TestCase,skipUnless

from thin_ai import search
from thin_rules import CRACK_TICKS,IDLE,NORTH_SHOAL,ROUND_TICKS,THIN,Control,State,ice_at,live_ice,step


class SkatingTests(TestCase):
    def test_dash_cracks_thin_ice_and_sinks_on_its_deadline(self):
        game=State(school_mask=0,respawn_at=1000)
        player=game.skaters[0]
        player.x=player.y=0.
        player.score=2
        events=[]
        cell=ice_at(0,0)
        step(game,(Control(1,0,dash=True),IDLE),events)
        self.assertEqual(game.ice[cell],game.tick+CRACK_TICKS)
        self.assertEqual([event[0] for event in events[:2]],["crack","dash"])
        for _ in range(CRACK_TICKS-1):
            step(game,(Control(brake=True),IDLE))
        self.assertGreater(game.ice[cell],game.tick)
        player.x=player.y=0.
        step(game,(Control(brake=True),IDLE),events)
        self.assertEqual(game.ice[cell],-1)
        self.assertEqual(player.score,1)
        self.assertGreater(player.splash,0)

    def test_one_shared_fish_goes_to_the_nearest_diver(self):
        game=State(school_x=0.,school_y=0.,school_mask=1)
        game.skaters[0].x=-.13
        game.skaters[0].y=game.skaters[1].y=0.
        game.skaters[1].x=.64
        step(game,(IDLE,IDLE))
        self.assertEqual([player.score for player in game.skaters],[1,0])
        self.assertEqual(game.school_mask,0)

    def test_brake_and_round_end(self):
        game=State(tick=ROUND_TICKS-1)
        game.skaters[0].vx=5.
        step(game,(Control(brake=True),IDLE))
        self.assertTrue(game.over)
        self.assertLess(game.skaters[0].vx,4.)
        after=game.clone()
        step(game,(IDLE,IDLE))
        self.assertEqual(game,after)

    def test_the_shoal_can_follow_the_northern_route_after_every_crack(self):
        game=State(north_route=True)
        for cell in THIN:
            game.ice[cell]=-1
        for a,b in zip(NORTH_SHOAL,(*NORTH_SHOAL[1:],NORTH_SHOAL[0])):
            for i in range(17):
                fraction=i/16
                self.assertTrue(live_ice(game,a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction))

    def test_both_algorithms_plan_without_editing_live_state(self):
        game=State()
        original=game.clone()
        for side,algorithm in enumerate(("Minimax","MCTS")):
            result=search(game,side,algorithm)
            self.assertGreater(result.effort,0)
            self.assertIsInstance(result.control,Control)
        self.assertEqual(game,original)


@skipUnless(find_spec("panda3d"),"Panda3D required")
class ArenaTests(TestCase):
    def test_same_camera_local_duel_moves_both_penguins(self):
        from panda3d.core import ConfigPageManager,loadPrcFileData
        from thin_ice import ThinIce

        prefs=loadPrcFileData("Thin Ice test","win-size 1100 720\nwindow-type offscreen\naudio-library-name null\nnotify-level error")
        self.addCleanup(ConfigPageManager.getGlobalPtr().deleteExplicitPage,prefs)
        game=ThinIce("offscreen",audio=False)
        self.addCleanup(game.destroy)
        game.choose(2)
        self.assertEqual(game.players,("Human","Human"))
        start=tuple(player.x for player in game.state.skaters)
        game.press("d")
        game.press("arrow_left")
        for _ in range(20):
            game.update(1/60)
        self.assertGreater(game.state.skaters[0].x,start[0])
        self.assertLess(game.state.skaters[1].x,start[1])
        self.assertEqual(len(game.stage.swimmers),2)
