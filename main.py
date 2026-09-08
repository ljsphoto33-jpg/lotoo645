#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
로또 6/45 번호 생성기 — 안드로이드 (Kivy)
========================================
PC 버전(lotto645_gui.py)과 동일한 기능을 휴대폰 화면에 맞춰 재구성했습니다.
분석 로직은 PC와 완전히 같은 lotto645.py 엔진을 그대로 씁니다.
"""

import csv
import os
import queue
import random
import sys
import threading
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
sys.path.insert(0, HERE)

from kivy.config import Config                                    # noqa: E402
if not os.environ.get("ANDROID_ARGUMENT"):                        # PC 테스트용
    Config.set("graphics", "width", "412")
    Config.set("graphics", "height", "892")

from kivy.app import App                                          # noqa: E402
from kivy.clock import Clock                                      # noqa: E402
from kivy.core.text import LabelBase                              # noqa: E402
from kivy.core.window import Window                               # noqa: E402
from kivy.graphics import Color, Ellipse, RoundedRectangle        # noqa: E402
from kivy.metrics import dp, sp                                   # noqa: E402
from kivy.uix.boxlayout import BoxLayout                          # noqa: E402
from kivy.uix.button import Button                                # noqa: E402
from kivy.uix.label import Label                                  # noqa: E402
from kivy.uix.popup import Popup                                  # noqa: E402
from kivy.uix.scrollview import ScrollView                        # noqa: E402
from kivy.uix.slider import Slider                                # noqa: E402
from kivy.uix.textinput import TextInput                          # noqa: E402
from kivy.uix.widget import Widget                                # noqa: E402

# 한글 폰트를 기본 폰트로 등록 (모든 위젯에 적용)
LabelBase.register(name="Roboto",
                   fn_regular=os.path.join(ASSETS, "NotoKR-Regular.ttf"),
                   fn_bold=os.path.join(ASSETS, "NotoKR-Bold.ttf"))

import lotto645 as engine                                         # noqa: E402

# ---------------------------------------------------------------------------
# 색상 (PC 버전과 동일한 하늘색 테마)
# ---------------------------------------------------------------------------

def rgba(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


BG       = rgba("d7ebfb")
CARD     = rgba("ffffff")
CARD_ALT = rgba("eaf5ff")
FG       = rgba("123049")
MUTED    = rgba("5b7f9e")
ACCENT   = rgba("1877d2")
ACCENT_D = rgba("125fa8")
GOOD     = rgba("0d7a45")
LINE     = rgba("a9d2ef")

BALLS = [(10, "fbc400", "3b2f00"), (20, "69c8f2", "00303f"),
         (30, "ff7272", "ffffff"), (40, "aaaaaa", "ffffff"),
         (45, "b0d840", "22300a")]

RANK_NAME = {1: "1등", 2: "2등", 3: "3등", 4: "4등", 5: "5등", 0: "낙첨"}
FIXED_PRIZE = {4: 50000, 5: 5000}
TICKET_PRICE = 1000
THEORY_P3 = 0.022441
THEORY_MEAN = 0.8
THEORY_ANY3_5G = 0.11965


def ball_colors(n):
    for hi, b, f in BALLS:
        if n <= hi:
            return rgba(b), rgba(f)
    return rgba("b0d840"), rgba("22300a")


# ---------------------------------------------------------------------------
# 예측 저장소 (PC 버전과 같은 predictions.csv 형식)
# ---------------------------------------------------------------------------

FIELDS = ["id", "saved_at", "target_draw", "nums", "matched", "bonus_hit", "rank"]


def pred_path():
    return os.path.join(engine.DATA_DIR, "predictions.csv")


def load_predictions():
    p = pred_path()
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "id": int(r["id"]),
                    "saved_at": r["saved_at"],
                    "target_draw": int(r["target_draw"]),
                    "nums": [int(x) for x in r["nums"].split()],
                    "matched": int(r["matched"]) if r["matched"] != "" else None,
                    "bonus_hit": r["bonus_hit"] == "1",
                    "rank": int(r["rank"]) if r["rank"] != "" else None,
                })
            except Exception:
                continue
    return rows


def save_predictions(rows):
    with open(pred_path(), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"id": r["id"], "saved_at": r["saved_at"],
                        "target_draw": r["target_draw"],
                        "nums": " ".join(str(n) for n in r["nums"]),
                        "matched": "" if r["matched"] is None else r["matched"],
                        "bonus_hit": "1" if r["bonus_hit"] else "0",
                        "rank": "" if r["rank"] is None else r["rank"]})


def append_predictions(target_draw, games):
    rows = load_predictions()
    nid = max((r["id"] for r in rows), default=0) + 1
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for g in games:
        rows.append({"id": nid, "saved_at": stamp, "target_draw": target_draw,
                     "nums": list(g), "matched": None, "bonus_hit": False,
                     "rank": None})
        nid += 1
    save_predictions(rows)
    return len(games)


def rank_of(m, bonus):
    if m == 6:
        return 1
    if m == 5 and bonus:
        return 2
    if m == 5:
        return 3
    if m == 4:
        return 4
    if m == 3:
        return 5
    return 0


def score_predictions(draws):
    by = {d["draw"]: d for d in draws}
    rows = load_predictions()
    n = 0
    for r in rows:
        if r["matched"] is not None:
            continue
        d = by.get(r["target_draw"])
        if not d:
            continue
        win = set(d["nums"])
        r["matched"] = len(win & set(r["nums"]))
        r["bonus_hit"] = d["bonus"] in r["nums"]
        r["rank"] = rank_of(r["matched"], r["bonus_hit"])
        n += 1
    if n:
        save_predictions(rows)
    return n


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return p, max(0.0, c - h), min(1.0, c + h)


# ---------------------------------------------------------------------------
# 기본 위젯
# ---------------------------------------------------------------------------

class Card(BoxLayout):
    """둥근 흰 카드."""

    def __init__(self, bg=CARD, radius=14, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._col = Color(*bg)
            self._rr = RoundedRectangle(radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._rr.pos = self.pos
        self._rr.size = self.size

    def set_bg(self, c):
        self._col.rgba = c


class TxT(Label):
    """줄바꿈·높이 자동 라벨."""

    def __init__(self, text="", size=13, color=FG, bold=False, halign="left", **kw):
        super().__init__(text=text, font_size=sp(size), color=color, bold=bold,
                         halign=halign, valign="top", markup=True, **kw)
        self.bind(width=lambda *a: setattr(self, "text_size", (self.width, None)))
        self.bind(texture_size=lambda *a: setattr(self, "height", self.texture_size[1]))
        self.size_hint_y = None


class Ball(Label):
    """번호 공 하나."""

    def __init__(self, num, **kw):
        bg, fg = ball_colors(num)
        super().__init__(text=str(num), bold=True, color=fg,
                         font_size=sp(15), **kw)
        with self.canvas.before:
            Color(1, 1, 1, 0.95)
            self._ring = Ellipse()
            Color(*bg)
            self._e = Ellipse()
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        d = min(self.width, self.height)
        self._ring.size = (d, d)
        self._ring.pos = (self.center_x - d / 2, self.center_y - d / 2)
        d2 = d - dp(3)
        self._e.size = (d2, d2)
        self._e.pos = (self.center_x - d2 / 2, self.center_y - d2 / 2)


class FlatButton(Button):
    def __init__(self, text="", primary=False, size=14, **kw):
        super().__init__(text=text, font_size=sp(size),
                         background_normal="", background_down="",
                         background_color=(0, 0, 0, 0),
                         disabled_color=MUTED, **kw)
        self.primary = primary
        base = ACCENT if primary else CARD
        self.color = rgba("ffffff") if primary else FG
        with self.canvas.before:
            self._col = Color(*base)
            self._rr = RoundedRectangle(radius=[dp(10)])
        self.bind(pos=self._sync, size=self._sync, state=self._press)

    def _sync(self, *a):
        self._rr.pos = self.pos
        self._rr.size = self.size

    def _press(self, *a):
        if self.disabled:
            self._col.rgba = rgba("9dc3e6") if self.primary else CARD_ALT
        elif self.state == "down":
            self._col.rgba = ACCENT_D if self.primary else CARD_ALT
        else:
            self._col.rgba = ACCENT if self.primary else CARD

    def on_disabled(self, *a):
        self._press()


def toast(title, message):
    root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
    sv = ScrollView()
    lbl = TxT(message, size=14)
    sv.add_widget(lbl)
    root.add_widget(sv)
    btn = FlatButton("확인", primary=True, size_hint_y=None, height=dp(46))
    root.add_widget(btn)
    p = Popup(title=title, content=root, size_hint=(0.92, None),
              height=dp(340), title_size=sp(15), separator_color=ACCENT)
    btn.bind(on_release=p.dismiss)
    p.open()
    return p


# ---------------------------------------------------------------------------
# 화면 1 — 번호 생성
# ---------------------------------------------------------------------------

class GenScreen(BoxLayout):

    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", spacing=dp(8),
                         padding=[dp(10), dp(8), dp(10), dp(10)], **kw)
        self.app = app
        self.n_games = 5
        self.disjoint = True
        self.autosave = True
        self.alpha = 0.35

        # ---- 옵션 카드 -------------------------------------------------
        opt = Card(orientation="vertical", size_hint_y=None,
                   padding=dp(12), spacing=dp(8))
        opt.bind(minimum_height=opt.setter("height"))

        r1 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        r1.add_widget(TxT("게임 수", size=13, color=MUTED, height=dp(40)))
        self.b_minus = FlatButton("-", size=20, size_hint_x=None, width=dp(44))
        self.lbl_n = Label(text="5", font_size=sp(17), bold=True, color=FG,
                           size_hint_x=None, width=dp(44))
        self.b_plus = FlatButton("+", size=20, size_hint_x=None, width=dp(44))
        self.b_minus.bind(on_release=lambda *a: self._bump(-1))
        self.b_plus.bind(on_release=lambda *a: self._bump(1))
        r1.add_widget(Widget())
        for w in (self.b_minus, self.lbl_n, self.b_plus):
            r1.add_widget(w)
        opt.add_widget(r1)

        self.t_disjoint = FlatButton("완전분산  켜짐", size=13,
                                     size_hint_y=None, height=dp(42))
        self.t_disjoint.bind(on_release=lambda *a: self._toggle("disjoint"))
        opt.add_widget(self.t_disjoint)

        self.t_autosave = FlatButton("자동 저장  켜짐", size=13,
                                     size_hint_y=None, height=dp(42))
        self.t_autosave.bind(on_release=lambda *a: self._toggle("autosave"))
        opt.add_widget(self.t_autosave)

        r3 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r3.add_widget(TxT("포함", size=12, color=MUTED, size_hint_x=None,
                          width=dp(34), height=dp(44)))
        self.in_inc = TextInput(text="", multiline=False, font_size=sp(14),
                                size_hint_y=None, height=dp(40),
                                foreground_color=FG, background_color=CARD_ALT,
                                padding=[dp(8), dp(10)], hint_text="7,13")
        r3.add_widget(self.in_inc)
        r3.add_widget(TxT("제외", size=12, color=MUTED, size_hint_x=None,
                          width=dp(34), height=dp(44)))
        self.in_exc = TextInput(text="", multiline=False, font_size=sp(14),
                                size_hint_y=None, height=dp(40),
                                foreground_color=FG, background_color=CARD_ALT,
                                padding=[dp(8), dp(10)], hint_text="4,44")
        r3.add_widget(self.in_exc)
        opt.add_widget(r3)

        r4 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.lbl_alpha = TxT("구간 가중 0.35\n완만", size=11, color=MUTED,
                             size_hint_x=None, width=dp(104))
        r4.add_widget(self.lbl_alpha)
        sld = Slider(min=0, max=1, value=0.35, step=0.05,
                     cursor_size=(dp(22), dp(22)))
        sld.bind(value=self._alpha)
        r4.add_widget(sld)
        opt.add_widget(r4)
        for w, on in ((self.t_disjoint, self.disjoint),
                      (self.t_autosave, self.autosave)):
            w.primary = on
            w.color = rgba("ffffff") if on else MUTED
            w._press()
        self.add_widget(opt)

        # ---- 생성 버튼 -------------------------------------------------
        self.btn_gen = FlatButton("번 호 생 성", primary=True, size=20,
                                  size_hint_y=None, height=dp(62), bold=True)
        self.btn_gen.bind(on_release=lambda *a: self.generate())
        self.add_widget(self.btn_gen)

        self.lbl_target = TxT("", size=11, color=MUTED)
        self.add_widget(self.lbl_target)

        # ---- 결과 -------------------------------------------------------
        self.sv = ScrollView()
        self.box = BoxLayout(orientation="vertical", spacing=dp(8),
                             size_hint_y=None, padding=[0, dp(2)])
        self.box.bind(minimum_height=self.box.setter("height"))
        self.sv.add_widget(self.box)
        self.add_widget(self.sv)

        self.lbl_saved = TxT("", size=11, color=GOOD)
        self.add_widget(self.lbl_saved)
        self._empty()

    # ------------------------------------------------------------------
    def _bump(self, d):
        self.n_games = max(1, min(10, self.n_games + d))
        self.lbl_n.text = str(self.n_games)

    def _toggle(self, which):
        setattr(self, which, not getattr(self, which))
        on = getattr(self, which)
        btn = self.t_disjoint if which == "disjoint" else self.t_autosave
        name = "완전분산" if which == "disjoint" else "자동 저장"
        btn.text = f"{name}  {'켜짐' if on else '꺼짐'}"
        btn.color = rgba("ffffff") if on else MUTED
        btn.primary = on
        btn._press()

    def _alpha(self, _s, v):
        self.alpha = float(v)
        tag = "균등" if v < 0.05 else ("완만" if v < 0.5 else "고빈도 편중")
        self.lbl_alpha.text = f"구간 가중 {v:.2f}\n{tag}"

    def _empty(self):
        self.box.clear_widgets()
        c = Card(orientation="vertical", size_hint_y=None, height=dp(120),
                 padding=dp(16), bg=CARD_ALT)
        c.add_widget(TxT("[b]번 호 생 성[/b] 버튼을 누르면\n"
                         "번호가 나옵니다.\n\n"
                         "누를 때마다 새 조합이 다시 나옵니다.",
                         size=13, color=MUTED, halign="center"))
        self.box.add_widget(c)

    def refresh_target(self):
        last = self.app.draws[-1]
        d = last["date"]
        self.lbl_target.text = (
            f"대상: 제 {last['draw']+1}회   ·   직전 {d[:4]}.{d[4:6]}.{d[6:]}  "
            f"{', '.join(map(str, last['nums']))} +{last['bonus']}")

    def _parse(self, s):
        out = []
        for tok in s.replace(",", " ").split():
            try:
                v = int(tok)
            except ValueError:
                continue
            if 1 <= v <= 45:
                out.append(v)
        return sorted(set(out))

    def generate(self):
        inc = self._parse(self.in_inc.text)
        exc = self._parse(self.in_exc.text)
        if set(inc) & set(exc):
            toast("입력 확인", "같은 번호를 포함과 제외에\n동시에 넣을 수 없습니다.")
            return
        if len(inc) > 5:
            toast("입력 확인", "포함할 번호는 5개까지만 가능합니다.")
            return
        try:
            games, cfg, _ = engine.generate(
                self.app.draws, self.n_games, self.alpha, inc, exc, 0.94,
                self.app.rng, max_overlap=0 if self.disjoint else 2)
        except Exception:
            toast("생성 실패", "조건이 너무 까다로워 조합을 만들지 못했습니다.\n"
                              "포함/제외 번호를 줄여 보세요.")
            return
        if not games:
            toast("생성 실패", "조건에 맞는 조합이 없습니다.")
            return

        self.box.clear_widgets()
        for i, g in enumerate(games):
            self.box.add_widget(self._game_card(i, g))

        target = self.app.draws[-1]["draw"] + 1
        if self.autosave:
            append_predictions(target, games)
            self.lbl_saved.text = (f"✓ 제 {target}회 예측으로 "
                                   f"{len(games)}게임 저장됨")
            self.app.analysis.refresh()
        else:
            self.lbl_saved.text = "자동 저장이 꺼져 있어 저장하지 않았습니다."

    def _game_card(self, i, g):
        c = Card(orientation="vertical", size_hint_y=None, height=dp(92),
                 padding=[dp(10), dp(8)], spacing=dp(2),
                 bg=CARD if i % 2 == 0 else CARD_ALT)
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(2))
        top.add_widget(Label(text=chr(65 + i), font_size=sp(15), bold=True,
                             color=MUTED, size_hint_x=None, width=dp(20)))
        for n in g:
            top.add_widget(Ball(n))
        c.add_widget(top)
        f = engine.features(g)
        c.add_widget(TxT(f"총합 {f['sum']}   홀짝 {f['odd']}:{6-f['odd']}   "
                         f"저고 {f['low']}:{6-f['low']}   AC {f['ac']}",
                         size=11, color=MUTED, halign="center"))
        return c


# ---------------------------------------------------------------------------
# 화면 2 — 저장 & 적중분석
# ---------------------------------------------------------------------------

class AnalysisScreen(BoxLayout):

    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", spacing=dp(8),
                         padding=[dp(10), dp(8), dp(10), dp(10)], **kw)
        self.app = app
        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b1 = FlatButton("당첨결과와 대조", primary=True, size=13)
        b1.bind(on_release=lambda *a: self.on_score())
        b2 = FlatButton("기록 전체 삭제", size=13, size_hint_x=None, width=dp(120))
        b2.bind(on_release=lambda *a: self.on_clear())
        bar.add_widget(b1)
        bar.add_widget(b2)
        self.add_widget(bar)

        self.sv = ScrollView()
        self.box = BoxLayout(orientation="vertical", spacing=dp(8),
                             size_hint_y=None)
        self.box.bind(minimum_height=self.box.setter("height"))
        self.sv.add_widget(self.box)
        self.add_widget(self.sv)

    def on_score(self):
        n = score_predictions(self.app.draws)
        self.refresh()
        if n:
            toast("대조 완료", f"{n}건을 채점했습니다.")
        else:
            pend = [r for r in load_predictions() if r["matched"] is None]
            if pend:
                nxt = min(r["target_draw"] for r in pend)
                toast("대기 중", f"제 {nxt}회는 아직 추첨 전이거나\n"
                                f"데이터가 없습니다.\n\n"
                                f"토요일 추첨 후 위쪽 [최신 회차 업데이트]를\n"
                                f"누르면 자동으로 대조됩니다.")
            else:
                toast("대조 완료", "새로 채점할 예측이 없습니다.")

    def on_clear(self):
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        content.add_widget(TxT("저장된 예측 기록을 모두 지웁니다.\n계속할까요?", size=14))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        yes = FlatButton("삭제", primary=True)
        no = FlatButton("취소")
        row.add_widget(no)
        row.add_widget(yes)
        content.add_widget(row)
        p = Popup(title="전체 삭제", content=content, size_hint=(0.9, None),
                  height=dp(220), title_size=sp(15), separator_color=ACCENT)
        no.bind(on_release=p.dismiss)

        def do(*a):
            save_predictions([])
            self.refresh()
            p.dismiss()
        yes.bind(on_release=do)
        p.open()

    # ------------------------------------------------------------------
    def refresh(self):
        self.box.clear_widgets()
        rows = load_predictions()
        done = [r for r in rows if r["matched"] is not None]
        pend = [r for r in rows if r["matched"] is None]

        if not rows:
            c = Card(orientation="vertical", size_hint_y=None, height=dp(150),
                     padding=dp(16))
            c.add_widget(TxT(
                "아직 저장된 예측이 없습니다.\n\n"
                "[번호 생성]에서 번호를 만들면 자동으로 쌓이고,\n"
                "토요일 추첨 후 [최신 회차 업데이트]를 누르면\n"
                "실제 당첨번호와 자동으로 대조됩니다.",
                size=13, color=MUTED))
            self.box.add_widget(c)
            return

        # ---- 요약 카드 ---------------------------------------------------
        c = Card(orientation="vertical", size_hint_y=None, padding=dp(14),
                 spacing=dp(6))
        c.bind(minimum_height=c.setter("height"))
        head = (f"전체 [b]{len(rows)}[/b]게임   ·   채점 [b]{len(done)}[/b]   ·   "
                f"대기 [b]{len(pend)}[/b]")
        c.add_widget(TxT(head, size=13))
        if pend:
            ds = sorted({r["target_draw"] for r in pend})
            c.add_widget(TxT("대기 회차: " + ", ".join(f"{d}회" for d in ds),
                             size=11, color=MUTED))

        if done:
            n = len(done)
            cnt = {k: 0 for k in range(7)}
            ranks = {k: 0 for k in range(6)}
            for r in done:
                cnt[r["matched"]] += 1
                ranks[r["rank"]] += 1

            c.add_widget(TxT("\n[b]적중 개수 분포[/b]", size=12))
            for k in range(7):
                if cnt[k] == 0 and k > 4:
                    continue
                bar = "█" * int(round(cnt[k] / n * 18))
                c.add_widget(TxT(f"{k}개  {cnt[k]:4d}게임 {cnt[k]/n*100:5.1f}%  "
                                 f"[color=1877d2]{bar}[/color]", size=11))

            parts = [f"{RANK_NAME[k]} {ranks[k]}건" for k in (1, 2, 3, 4, 5)
                     if ranks[k]]
            c.add_widget(TxT("\n[b]등수[/b]  " +
                             (" · ".join(parts) if parts else "당첨 없음") +
                             f"  ·  낙첨 {ranks[0]}건", size=12))

            k3 = sum(cnt[i] for i in range(3, 7))
            p3, lo, hi = wilson(k3, n)
            mean = sum(k * cnt[k] for k in cnt) / n
            inside = lo <= THEORY_P3 <= hi
            c.add_widget(TxT(
                f"\n[b]이론값 대비[/b]\n"
                f"3개 이상 적중률  실측 {p3*100:.3f}%\n"
                f"95% 신뢰구간  [{lo*100:.3f}% ~ {hi*100:.3f}%]\n"
                f"이론 {THEORY_P3*100:.3f}%  → "
                + (f"[color=0d7a45]신뢰구간 안 (정상)[/color]" if inside
                   else "[color=b06a00]신뢰구간 밖[/color]") +
                f"\n평균 적중  실측 {mean:.3f}  /  이론 {THEORY_MEAN:.3f}",
                size=12))
            if n < 200:
                c.add_widget(TxT(f"※ 표본이 {n}게임뿐이라 오차가 큽니다.",
                                 size=11, color=MUTED))

            by_draw = {}
            for r in done:
                by_draw.setdefault(r["target_draw"], []).append(r)
            hit = sum(1 for v in by_draw.values()
                      if any(x["matched"] >= 3 for x in v))
            c.add_widget(TxT(
                f"\n회차 단위: {len(by_draw)}회 중 {hit}회에서 한 게임 이상 "
                f"3개+ 적중 ({hit/len(by_draw)*100:.1f}%)\n"
                f"참고 이론값(완전분산 5게임) {THEORY_ANY3_5G*100:.2f}%",
                size=11, color=MUTED))

            spend = n * TICKET_PRICE
            fixed = ranks[4] * FIXED_PRIZE[4] + ranks[5] * FIXED_PRIZE[5]
            c.add_widget(TxT(
                f"\n[b]손익[/b] (게임당 1,000원)\n"
                f"구매 {spend:,}원 · 당첨 {fixed:,}원 · 수지 {fixed-spend:+,}원",
                size=12))
        else:
            c.add_widget(TxT("\n아직 채점된 게임이 없습니다.\n추첨 후 다시 확인해 주세요.",
                             size=12, color=MUTED))
        self.box.add_widget(c)

        # ---- 목록 --------------------------------------------------------
        for r in sorted(rows, key=lambda x: (-x["target_draw"], -x["id"]))[:120]:
            self.box.add_widget(self._row_card(r))

    def _row_card(self, r):
        c = Card(orientation="vertical", size_hint_y=None, height=dp(74),
                 padding=[dp(10), dp(6)], spacing=dp(2),
                 bg=CARD if r["rank"] in (None, 0) else rgba("e6f7ee"))
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(2))
        for n in r["nums"]:
            top.add_widget(Ball(n))
        c.add_widget(top)
        if r["matched"] is None:
            info = f"[color=5b7f9e]{r['target_draw']}회 · 추첨 전[/color]"
        else:
            tag = ("[color=0d7a45][b]" + RANK_NAME[r["rank"]] + "[/b][/color]"
                   if r["rank"] else "[color=5b7f9e]낙첨[/color]")
            bonus = " +보너스" if (r["bonus_hit"] and r["matched"] == 5) else ""
            info = (f"[color=5b7f9e]{r['target_draw']}회 · "
                    f"{r['matched']}개 적중{bonus} · [/color]{tag}")
        c.add_widget(TxT(info, size=11, halign="center"))
        return c


# ---------------------------------------------------------------------------
# 화면 3 — 구간 통계
# ---------------------------------------------------------------------------

def mobile_stats(draws, alpha=0.35):
    """휴대폰 폭에 맞춘 구간 통계 텍스트 (markup)."""
    a = engine.analyze(draws)
    cfg = engine.calibrate(draws, 0.94)
    last = draws[-1]
    d = last["date"]
    L = []
    L.append(f"[b]총 {len(draws)}회차[/b]  (1회 ~ {last['draw']}회)")
    L.append(f"[color=5b7f9e]직전 {d[:4]}.{d[4:6]}.{d[6:]}[/color]  "
             f"{', '.join(map(str, last['nums']))} +{last['bonus']}")

    L.append("\n[b]■ 구간별 고빈도 / 저빈도[/b]")
    for name, info in a["windows"].items():
        hot = ", ".join(f"{n}({info['counts'][n]})" for n in info["hot"][:5])
        cold = ", ".join(f"{n}({info['counts'].get(n,0)})" for n in info["cold"][:5])
        L.append(f"[color=1877d2][b]{name}[/b][/color] "
                 f"[color=5b7f9e](최근 {info['w']}회, 기대 {info['expected']:.1f})[/color]")
        L.append(f"  많이: {hot}")
        L.append(f"  적게: {cold}")

    score, _ = engine.number_scores(draws, alpha)
    ranked = sorted(range(1, 46), key=lambda n: -score[n])
    L.append("\n[b]■ 종합 점수 (3/4/5/6개월 가중)[/b]")
    L.append("[color=5b7f9e]상위[/color]  " +
             "  ".join(f"[b]{n}[/b]({score[n]:.2f})" for n in ranked[:8]))
    L.append("[color=5b7f9e]하위[/color]  " +
             "  ".join(f"{n}({score[n]:.2f})" for n in ranked[-8:]))

    g = sorted(a["gaps"].items(), key=lambda kv: -kv[1])[:8]
    L.append("\n[b]■ 오래 안 나온 번호[/b]")
    L.append("  " + "  ".join(f"{n}번:{v}회" for n, v in g))

    tot = sum(a["carry_hist"].values())
    L.append("\n[b]■ 이월번호 (직전 회차 재출현)[/b]")
    for k in sorted(a["carry_hist"]):
        c = a["carry_hist"][k]
        L.append(f"  {k}개 {c:4d}회 {c/tot*100:5.1f}%  "
                 f"[color=1877d2]{'█'*int(round(c/tot*20))}[/color]")
    L.append(f"  [color=5b7f9e]평균 {a['carry_mean']:.2f}개 — "
             f"전부 빼는 것은 과도한 필터[/color]")

    tot = sum(a["consec_hist"].values())
    L.append("\n[b]■ 연속번호 쌍[/b]")
    for k in sorted(a["consec_hist"]):
        c = a["consec_hist"][k]
        L.append(f"  {k}쌍 {c:4d}회 {c/tot*100:5.1f}%  "
                 f"[color=1877d2]{'█'*int(round(c/tot*20))}[/color]")

    L.append("\n[b]■ 자동 산출된 필터 경계[/b]")
    L.append(f"[color=5b7f9e]역대 당첨조합 분포에서 계산[/color]")
    L.append(f"  총합 {cfg['sum_min']}~{cfg['sum_max']}   "
             f"끝수합 {cfg['tail_min']}~{cfg['tail_max']}")
    L.append(f"  AC {cfg['ac_min']}+   최장연속 {cfg['max_run']}   "
             f"연속쌍 {cfg['consec_max']}")
    L.append(f"  구간 최소 {cfg['zones_min']}개 / 한 구간 최대 {cfg['max_zone']}개")
    L.append(f"  이월 가중 {cfg['carry_penalty']}배, 최대 {cfg['carry_max']}개")
    L.append(f"  32~45 최소 {cfg['min_over31']}개 (생일수 편중 회피)")

    L.append("\n[color=5b7f9e]※ 1등 확률은 어떤 번호든 1/8,145,060 로 동일합니다. "
             "위 조건은 확률을 올리는 것이 아니라, 당첨 시 나눠 갖는 인원을 줄이고 "
             "구조적으로 비정상적인 조합을 걸러내기 위한 것입니다.[/color]")
    return "\n".join(L)


class StatsScreen(BoxLayout):

    def __init__(self, app, **kw):
        super().__init__(orientation="vertical",
                         padding=[dp(10), dp(8), dp(10), dp(10)], **kw)
        self.app = app
        self.sv = ScrollView()
        self.card = Card(orientation="vertical", size_hint_y=None,
                         padding=dp(14))
        self.card.bind(minimum_height=self.card.setter("height"))
        self.lbl = TxT("", size=12)
        self.card.add_widget(self.lbl)
        self.sv.add_widget(self.card)
        self.add_widget(self.sv)

    def refresh(self):
        try:
            self.lbl.text = mobile_stats(self.app.draws, self.app.gen.alpha)
        except Exception:
            self.lbl.text = "[color=b06a00]통계를 계산하지 못했습니다.[/color]"


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------

class LottoApp(App):

    def build(self):
        self.title = "로또 6/45 번호 생성기"
        Window.clearcolor = BG
        self.rng = random.Random()
        self.busy = False

        # 데이터 폴더: 안드로이드는 앱 전용 저장소
        engine.set_data_dir(self.user_data_dir,
                            seed_from=os.path.join(ASSETS, "lotto645_history.csv"))
        self.draws = engine.load_draws()

        root = BoxLayout(orientation="vertical")

        # ---- 헤더 -------------------------------------------------------
        head = Card(orientation="vertical", size_hint_y=None, height=dp(84),
                    padding=[dp(12), dp(8)], spacing=dp(2), radius=0, bg=CARD)
        r = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        r.add_widget(Label(text="로또 6/45", font_size=sp(18), bold=True,
                           color=FG, halign="left", size_hint_x=None,
                           width=dp(110)))
        self.btn_update = FlatButton("최신 회차 업데이트", size=12,
                                     size_hint_x=None, width=dp(150))
        self.btn_update.bind(on_release=lambda *a: self.do_update())
        r.add_widget(Widget())
        r.add_widget(self.btn_update)
        head.add_widget(r)
        self.lbl_head = TxT("", size=11, color=MUTED)
        head.add_widget(self.lbl_head)
        root.add_widget(head)

        # ---- 탭 ---------------------------------------------------------
        self.gen = GenScreen(self)
        self.analysis = AnalysisScreen(self)
        self.stats = StatsScreen(self)
        self.screens = [self.gen, self.analysis, self.stats]

        tabbar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(2),
                           padding=[dp(6), dp(4), dp(6), 0])
        self.tabs = []
        for i, name in enumerate(("번호 생성", "적중 분석", "구간 통계")):
            b = FlatButton(name, size=13)
            b.bind(on_release=lambda _b, k=i: self.show(k))
            tabbar.add_widget(b)
            self.tabs.append(b)
        root.add_widget(tabbar)

        self.body = BoxLayout()
        root.add_widget(self.body)

        self.show(0)
        self.refresh_header()
        self.analysis.refresh()
        Clock.schedule_once(lambda *a: self.stats.refresh(), 0.4)
        Clock.schedule_once(lambda *a: self.auto_update(), 1.2)
        return root

    # ------------------------------------------------------------------
    def show(self, k):
        self.body.clear_widgets()
        self.body.add_widget(self.screens[k])
        for i, b in enumerate(self.tabs):
            b.primary = (i == k)
            b.color = rgba("ffffff") if i == k else MUTED
            b._press()

    def refresh_header(self):
        last = self.draws[-1]
        d = last["date"]
        try:
            behind = engine.expected_latest_draw() - last["draw"]
        except Exception:
            behind = 0
        note = (f"[color=b06a00]● 새 회차 {behind}건[/color]" if behind > 0
                else "[color=0d7a45]● 최신 상태[/color]")
        self.lbl_head.text = (f"데이터 {len(self.draws)}회차 · 최신 "
                              f"{last['draw']}회 ({d[:4]}.{d[4:6]}.{d[6:]})   {note}")
        self.gen.refresh_target()

    # ------------------------------------------------------------------
    def auto_update(self):
        try:
            if engine.expected_latest_draw() > self.draws[-1]["draw"]:
                self.do_update(silent=True)
        except Exception:
            pass

    def do_update(self, silent=False):
        if self.busy:
            return
        self.busy = True
        self.btn_update.text = "조회 중 ..."
        self.btn_update.disabled = True
        box = {}

        def work():
            try:
                box["r"] = engine.update_history()
            except Exception:
                box["err"] = traceback.format_exc()
            Clock.schedule_once(lambda *a: done(), 0)

        def done():
            self.busy = False
            self.btn_update.text = "최신 회차 업데이트"
            self.btn_update.disabled = False
            if "err" in box:
                if not silent:
                    toast("업데이트 실패", "오류가 발생했습니다.\n\n" +
                          box["err"].strip().splitlines()[-1])
                return
            r = box["r"]
            self.draws = engine.load_draws()
            self.refresh_header()
            self.stats.refresh()
            scored = score_predictions(self.draws)
            self.analysis.refresh()
            if r["added"]:
                row = r["row"]
                d = row["date"]
                msg = (f"{r['added']}개 회차를 새로 받았습니다.\n\n"
                       f"제 {r['newest']}회 ({d[:4]}.{d[4:6]}.{d[6:]})\n"
                       f"{', '.join(map(str, row['nums']))} + 보너스 {row['bonus']}\n\n"
                       f"구간 통계와 번호 생성이 최신 데이터로 갱신되었습니다.")
                if scored:
                    msg += f"\n저장된 예측 {scored}건을 채점했습니다."
                toast("업데이트 완료", msg)
            elif r["reached"]:
                if not silent:
                    toast("업데이트", f"이미 최신 상태입니다. (제 {r['newest']}회)")
            else:
                if not silent:
                    toast("연결 실패",
                          "동행복권 서버에 연결하지 못했습니다.\n\n"
                          "· 인터넷 연결을 확인해 주세요\n"
                          "· 데이터 절약 모드가 켜져 있으면 꺼 주세요\n\n"
                          "연결이 안 되어도 기존 데이터로\n번호 생성은 정상 동작합니다.")

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    LottoApp().run()
