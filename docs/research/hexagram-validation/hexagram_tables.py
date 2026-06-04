"""
易经深层结构查表模块（研究原型）

所有计算都是确定性的——给定卦名或序号，推导上下卦、爻、互卦、
错卦、综卦、爻变、五行关系、应关系。零 LLM 调用。

用途：Journey Tracking 研究阶段的结构推导原型。
位置：docs/research/hexagram-validation/（研究目录，非生产代码）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# 八卦基础
# ---------------------------------------------------------------------------

TRIGRAMS: dict[str, dict] = {
    # name → {lines: (bottom,mid,top), nature, element, keyword}
    "乾": {"lines": (1, 1, 1), "nature": "天", "element": "金", "keyword": "刚健"},
    "兑": {"lines": (1, 1, 0), "nature": "泽", "element": "金", "keyword": "喜悦"},
    "离": {"lines": (1, 0, 1), "nature": "火", "element": "火", "keyword": "光明"},
    "震": {"lines": (1, 0, 0), "nature": "雷", "element": "木", "keyword": "震动"},
    "巽": {"lines": (0, 1, 1), "nature": "风", "element": "木", "keyword": "渗透"},
    "坎": {"lines": (0, 1, 0), "nature": "水", "element": "水", "keyword": "险陷"},
    "艮": {"lines": (0, 0, 1), "nature": "山", "element": "土", "keyword": "静止"},
    "坤": {"lines": (0, 0, 0), "nature": "地", "element": "土", "keyword": "柔顺"},
}

# 五行生克
GENERATION = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
GENERATED_BY = {v: k for k, v in GENERATION.items()}

CONTROL = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
CONTROLLED_BY = {v: k for k, v in CONTROL.items()}


def element_relation(a: str, b: str) -> Literal["生", "被生", "克", "被克", "同"]:
    """a 对 b 的五行关系。"""
    ea, eb = a, b
    if ea == eb:
        return "同"
    if GENERATION.get(ea) == eb:
        return "生"
    if GENERATED_BY.get(ea) == eb:
        return "被生"
    if CONTROL.get(ea) == eb:
        return "克"
    return "被克"


# ---------------------------------------------------------------------------
# 六十四卦：King Wen 序列
# 格式：序号 → (卦名, 上卦, 下卦)
# ---------------------------------------------------------------------------

HEXAGRAM_SEQUENCE: dict[int, tuple[str, str, str]] = {
    1:  ("乾",   "乾", "乾"),
    2:  ("坤",   "坤", "坤"),
    3:  ("屯",   "坎", "震"),
    4:  ("蒙",   "艮", "坎"),
    5:  ("需",   "坎", "乾"),
    6:  ("讼",   "乾", "坎"),
    7:  ("师",   "坤", "坎"),
    8:  ("比",   "坎", "坤"),
    9:  ("小畜", "巽", "乾"),
    10: ("履",   "乾", "兑"),
    11: ("泰",   "坤", "乾"),
    12: ("否",   "乾", "坤"),
    13: ("同人", "乾", "离"),
    14: ("大有", "离", "乾"),
    15: ("谦",   "坤", "艮"),
    16: ("豫",   "震", "坤"),
    17: ("随",   "兑", "震"),
    18: ("蛊",   "艮", "巽"),
    19: ("临",   "坤", "兑"),
    20: ("观",   "巽", "坤"),
    21: ("噬嗑", "离", "震"),
    22: ("贲",   "艮", "离"),
    23: ("剥",   "艮", "坤"),
    24: ("复",   "坤", "震"),
    25: ("无妄", "乾", "震"),
    26: ("大畜", "艮", "乾"),
    27: ("颐",   "艮", "震"),
    28: ("大过", "兑", "巽"),
    29: ("坎",   "坎", "坎"),
    30: ("离",   "离", "离"),
    31: ("咸",   "兑", "艮"),
    32: ("恒",   "震", "巽"),
    33: ("遁",   "乾", "艮"),
    34: ("大壮", "震", "乾"),
    35: ("晋",   "离", "坤"),
    36: ("明夷", "坤", "离"),
    37: ("家人", "巽", "离"),
    38: ("睽",   "离", "兑"),
    39: ("蹇",   "坎", "艮"),
    40: ("解",   "震", "坎"),
    41: ("损",   "艮", "兑"),
    42: ("益",   "巽", "震"),
    43: ("夬",   "兑", "乾"),
    44: ("姤",   "乾", "巽"),
    45: ("萃",   "兑", "坤"),
    46: ("升",   "坤", "巽"),
    47: ("困",   "兑", "坎"),
    48: ("井",   "坎", "巽"),
    49: ("革",   "兑", "离"),
    50: ("鼎",   "离", "巽"),
    51: ("震",   "震", "震"),
    52: ("艮",   "艮", "艮"),
    53: ("渐",   "巽", "艮"),
    54: ("归妹", "震", "兑"),
    55: ("丰",   "震", "离"),
    56: ("旅",   "离", "艮"),
    57: ("巽",   "巽", "巽"),
    58: ("兑",   "兑", "兑"),
    59: ("涣",   "巽", "坎"),
    60: ("节",   "坎", "兑"),
    61: ("中孚", "巽", "兑"),
    62: ("小过", "震", "艮"),
    63: ("既济", "坎", "离"),
    64: ("未济", "离", "坎"),
}

# 反向索引：卦名 → 序号
HEX_BY_NAME: dict[str, int] = {v[0]: k for k, v in HEXAGRAM_SEQUENCE.items()}


# ---------------------------------------------------------------------------
# 爻辞（384 条）
# 格式：(卦名, 爻位 1-6) → 爻辞文本
# 爻位从下往上：1=初爻，6=上爻
# ---------------------------------------------------------------------------

LINE_TEXTS: dict[tuple[str, int], str] = {
    # -- 乾 (1) --
    ("乾", 1): "潜龙勿用",
    ("乾", 2): "见龙在田，利见大人",
    ("乾", 3): "君子终日乾乾，夕惕若，厉无咎",
    ("乾", 4): "或跃在渊，无咎",
    ("乾", 5): "飞龙在天，利见大人",
    ("乾", 6): "亢龙有悔",
    # -- 坤 (2) --
    ("坤", 1): "履霜，坚冰至",
    ("坤", 2): "直方大，不习无不利",
    ("坤", 3): "含章可贞，或从王事，无成有终",
    ("坤", 4): "括囊，无咎无誉",
    ("坤", 5): "黄裳，元吉",
    ("坤", 6): "龙战于野，其血玄黄",
    # -- 屯 (3) --
    ("屯", 1): "磐桓，利居贞，利建侯",
    ("屯", 2): "屯如邅如，乘马班如，匪寇婚媾，女子贞不字，十年乃字",
    ("屯", 3): "即鹿无虞，惟入于林中，君子几不如舍，往吝",
    ("屯", 4): "乘马班如，求婚媾，往吉，无不利",
    ("屯", 5): "屯其膏，小贞吉，大贞凶",
    ("屯", 6): "乘马班如，泣血涟如",
    # -- 蒙 (4) --
    ("蒙", 1): "发蒙，利用刑人，用说桎梏，以往吝",
    ("蒙", 2): "包蒙吉，纳妇吉，子克家",
    ("蒙", 3): "勿用取女，见金夫，不有躬，无攸利",
    ("蒙", 4): "困蒙，吝",
    ("蒙", 5): "童蒙，吉",
    ("蒙", 6): "击蒙，不利为寇，利御寇",
    # -- 需 (5) --
    ("需", 1): "需于郊，利用恒，无咎",
    ("需", 2): "需于沙，小有言，终吉",
    ("需", 3): "需于泥，致寇至",
    ("需", 4): "需于血，出自穴",
    ("需", 5): "需于酒食，贞吉",
    ("需", 6): "入于穴，有不速之客三人来，敬之终吉",
    # -- 讼 (6) --
    ("讼", 1): "不永所事，小有言，终吉",
    ("讼", 2): "不克讼，归而逋其邑人三百户，无眚",
    ("讼", 3): "食旧德，贞厉，终吉，或从王事，无成",
    ("讼", 4): "不克讼，复即命渝，安贞吉",
    ("讼", 5): "讼元吉",
    ("讼", 6): "或锡之鞶带，终朝三褫之",
    # -- 泰 (11) --
    ("泰", 1): "拔茅茹以其汇，征吉",
    ("泰", 2): "包荒，用冯河，不遐遗，朋亡，得尚于中行",
    ("泰", 3): "无平不陂，无往不复，艰贞无咎，勿恤其孚，于食有福",
    ("泰", 4): "翩翩不富以其邻，不戒以孚",
    ("泰", 5): "帝乙归妹以祉，元吉",
    ("泰", 6): "城复于隍，勿用师，自邑告命，贞吝",
    # -- 否 (12) --
    ("否", 1): "拔茅茹以其汇，贞吉亨",
    ("否", 2): "包承，小人吉，大人否亨",
    ("否", 3): "包羞",
    ("否", 4): "有命无咎，畴离祉",
    ("否", 5): "休否，大人吉，其亡其亡，系于苞桑",
    ("否", 6): "倾否，先否后喜",
    # -- 谦 (15) --
    ("谦", 1): "谦谦君子，用涉大川，吉",
    ("谦", 2): "鸣谦，贞吉",
    ("谦", 3): "劳谦君子，有终吉",
    ("谦", 4): "无不利，撝谦",
    ("谦", 5): "不富以其邻，利用侵伐，无不利",
    ("谦", 6): "鸣谦，利用行师，征邑国",
    # -- 豫 (16) --
    ("豫", 1): "鸣豫，凶",
    ("豫", 2): "介于石，不终日，贞吉",
    ("豫", 3): "盱豫，悔，迟有悔",
    ("豫", 4): "由豫，大有得，勿疑朋盍簪",
    ("豫", 5): "贞疾，恒不死",
    ("豫", 6): "冥豫，成有渝，无咎",
    # -- 蛊 (18) --
    ("蛊", 1): "干父之蛊，有子考无咎，厉终吉",
    ("蛊", 2): "干母之蛊，不可贞",
    ("蛊", 3): "干父之蛊，小有悔，无大咎",
    ("蛊", 4): "裕父之蛊，往见吝",
    ("蛊", 5): "干父之蛊，用誉",
    ("蛊", 6): "不事王侯，高尚其事",
    # -- 临 (19) --
    ("临", 1): "咸临，贞吉",
    ("临", 2): "咸临，吉无不利",
    ("临", 3): "甘临，无攸利，既忧之，无咎",
    ("临", 4): "至临，无咎",
    ("临", 5): "知临，大君之宜，吉",
    ("临", 6): "敦临，吉无咎",
    # -- 观 (20) --
    ("观", 1): "童观，小人无咎，君子吝",
    ("观", 2): "闚观，利女贞",
    ("观", 3): "观我生进退",
    ("观", 4): "观国之光，利用宾于王",
    ("观", 5): "观我生，君子无咎",
    ("观", 6): "观其生，君子无咎",
    # -- 剥 (23) --
    ("剥", 1): "剥床以足，蔑贞凶",
    ("剥", 2): "剥床以辨，蔑贞凶",
    ("剥", 3): "剥之无咎",
    ("剥", 4): "剥床以肤，凶",
    ("剥", 5): "贯鱼以宫人宠，无不利",
    ("剥", 6): "硕果不食，君子得舆，小人剥庐",
    # -- 复 (24) --
    ("复", 1): "不远复，无祗悔，元吉",
    ("复", 2): "休复，吉",
    ("复", 3): "频复，厉无咎",
    ("复", 4): "中行独复",
    ("复", 5): "敦复，无悔",
    ("复", 6): "迷复，凶，有灾眚",
    # -- 咸 (31) --
    ("咸", 1): "咸其拇",
    ("咸", 2): "咸其腓，凶，居吉",
    ("咸", 3): "咸其股，执其随，往吝",
    ("咸", 4): "贞吉悔亡，憧憧往来，朋从尔思",
    ("咸", 5): "咸其脢，无悔",
    ("咸", 6): "咸其辅颊舌",
    # -- 恒 (32) --
    ("恒", 1): "浚恒，贞凶，无攸利",
    ("恒", 2): "悔亡",
    ("恒", 3): "不恒其德，或承之羞，贞吝",
    ("恒", 4): "田无禽",
    ("恒", 5): "恒其德贞，妇人吉，夫子凶",
    ("恒", 6): "振恒，凶",
    # -- 革 (49) --
    ("革", 1): "巩用黄牛之革",
    ("革", 2): "己日乃革之，征吉，无咎",
    ("革", 3): "征凶，贞厉，革言三就，有孚",
    ("革", 4): "悔亡，有孚改命，吉",
    ("革", 5): "大人虎变，未占有孚",
    ("革", 6): "君子豹变，小人革面，征凶，居贞吉",
    # -- 鼎 (50) --
    ("鼎", 1): "鼎颠趾，利出否，得妾以其子，无咎",
    ("鼎", 2): "鼎有实，我仇有疾，不我能即，吉",
    ("鼎", 3): "鼎耳革，其行塞，雉膏不食，方雨亏悔，终吉",
    ("鼎", 4): "鼎折足，覆公餗，其形渥，凶",
    ("鼎", 5): "鼎黄耳金铉，利贞",
    ("鼎", 6): "鼎玉铉，大吉，无不利",
    # -- 既济 (63) --
    ("既济", 1): "曳其轮，濡其尾，无咎",
    ("既济", 2): "妇丧其茀，勿逐，七日得",
    ("既济", 3): "高宗伐鬼方，三年克之，小人勿用",
    ("既济", 4): "繻有衣袽，终日戒",
    ("既济", 5): "东邻杀牛，不如西邻之禴祭，实受其福",
    ("既济", 6): "濡其首，厉",
    # -- 未济 (64) --
    ("未济", 1): "濡其尾，吝",
    ("未济", 2): "曳其轮，贞吉",
    ("未济", 3): "未济征凶，利涉大川",
    ("未济", 4): "贞吉悔亡，震用伐鬼方，三年有赏于大国",
    ("未济", 5): "贞吉无悔，君子之光有孚，吉",
    ("未济", 6): "有孚于饮酒，无咎，濡其首，有孚失是",
    # -- 渐 (53) --
    ("渐", 1): "鸿渐于干，小子厉有言，无咎",
    ("渐", 2): "鸿渐于磐，饮食衎衎，吉",
    ("渐", 3): "鸿渐于陆，夫征不复，妇孕不育，凶，利御寇",
    ("渐", 4): "鸿渐于木，或得其桷，无咎",
    ("渐", 5): "鸿渐于陵，妇三岁不孕，终莫之胜，吉",
    ("渐", 6): "鸿渐于陆，其羽可用为仪，吉",
    # -- 涣 (59) --
    ("涣", 1): "用拯马壮，吉",
    ("涣", 2): "涣奔其机，悔亡",
    ("涣", 3): "涣其躬，无悔",
    ("涣", 4): "涣其群，元吉，涣有丘，匪夷所思",
    ("涣", 5): "涣汗其大号，涣王居，无咎",
    ("涣", 6): "涣其血去逖出，无咎",
}


# ---------------------------------------------------------------------------
# HexArc：一个卦的完整结构推导
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HexArc:
    """一个卦象的结构化表示。给定卦名后，所有衍生结构由确定性计算得出。"""

    name: str  # 卦名，如 "屯"

    # ---- 基础属性（查表） ----

    @property
    def sequence_number(self) -> int:
        return HEX_BY_NAME[self.name]

    @property
    def upper_trigram(self) -> str:
        return HEXAGRAM_SEQUENCE[self.sequence_number][1]

    @property
    def lower_trigram(self) -> str:
        return HEXAGRAM_SEQUENCE[self.sequence_number][2]

    @property
    def upper_nature(self) -> str:
        return TRIGRAMS[self.upper_trigram]["nature"]

    @property
    def lower_nature(self) -> str:
        return TRIGRAMS[self.lower_trigram]["nature"]

    @property
    def lines(self) -> tuple[int, ...]:
        """六爻，从初爻（底）到上爻（顶）。"""
        lt = TRIGRAMS[self.lower_trigram]["lines"]
        ut = TRIGRAMS[self.upper_trigram]["lines"]
        return lt + ut  # (1,2,3,4,5,6)

    # ---- 五行关系 ----

    @property
    def upper_element(self) -> str:
        return TRIGRAMS[self.upper_trigram]["element"]

    @property
    def lower_element(self) -> str:
        return TRIGRAMS[self.lower_trigram]["element"]

    @property
    def internal_element_relation(self) -> str:
        """上下卦之间的五行关系。"""
        return element_relation(self.upper_element, self.lower_element)

    # ---- 衍生卦象（确定性计算） ----

    @property
    def nuclear(self) -> HexArc:
        """互卦：取 2-3-4 爻为下卦，3-4-5 爻为上卦。"""
        ln = self.lines
        lower = (ln[1], ln[2], ln[3])  # 爻 2,3,4
        upper = (ln[2], ln[3], ln[4])  # 爻 3,4,5
        return _from_trigram_lines(upper, lower)

    @property
    def inverse(self) -> HexArc:
        """错卦：所有爻阴阳取反。"""
        inv = tuple(1 - l for l in self.lines)
        return _from_hex_lines(inv)

    @property
    def reverse(self) -> HexArc:
        """综卦：整个卦颠倒（上下翻转）。"""
        rev = tuple(reversed(self.lines))
        return _from_hex_lines(rev)

    # ---- 爻变 ----

    def transitions_to(self, other: HexArc) -> list[int]:
        """返回从 self 到 other 变了哪些爻（1-indexed, 1=初爻, 6=上爻）。"""
        return [i + 1 for i in range(6) if self.lines[i] != other.lines[i]]

    def possible_single_changes(self) -> list[HexArc]:
        """枚举所有单爻变产生的卦（最多 6 个）。"""
        results = []
        for i in range(6):
            new_lines = list(self.lines)
            new_lines[i] = 1 - new_lines[i]
            results.append(_from_hex_lines(tuple(new_lines)))
        return results

    # ---- 序卦邻接 ----

    @property
    def wen_prev(self) -> HexArc | None:
        """King Wen 序列中的前一卦。"""
        n = self.sequence_number
        if n <= 1:
            return None
        name = HEXAGRAM_SEQUENCE[n - 1][0]
        return HexArc(name=name)

    @property
    def wen_next(self) -> HexArc | None:
        """King Wen 序列中的后一卦。"""
        n = self.sequence_number
        if n >= 64:
            return None
        name = HEXAGRAM_SEQUENCE[n + 1][0]
        return HexArc(name=name)

    # ---- 应关系 ----

    @property
    def correspondences(self) -> list[tuple[int, int, bool]]:
        """三对应关系：(内爻位, 外爻位, 是否相应)。
        1↔4, 2↔5, 3↔6。相应 = 一阴一阳。"""
        ln = self.lines
        pairs = [(1, 4), (2, 5), (3, 6)]
        result = []
        for inner, outer in pairs:
            responding = ln[inner - 1] != ln[outer - 1]
            result.append((inner, outer, responding))
        return result

    @property
    def correspondence_health(self) -> float:
        """应关系健康度：三对中有几对相应（0.0-1.0）。"""
        responding = sum(1 for _, _, r in self.correspondences if r)
        return responding / 3.0

    # ---- 爻辞 ----

    def line_text(self, position: int) -> str | None:
        """获取指定爻位的爻辞（1-6）。"""
        return LINE_TEXTS.get((self.name, position))

    # ---- 序列比较工具 ----

    def element_sequence_distance(self, other: HexArc) -> dict:
        """比较两段 Journey 的上下卦五行序列关系。"""
        return {
            "upper_relation": element_relation(
                self.upper_element, other.upper_element
            ),
            "lower_relation": element_relation(
                self.lower_element, other.lower_element
            ),
        }

    def structural_similarity(self, other: HexArc) -> dict:
        """结构相似度：共享几个三爻？上卦/下卦各是否相同？"""
        return {
            "same_upper": self.upper_trigram == other.upper_trigram,
            "same_lower": self.lower_trigram == other.lower_trigram,
            "shared_trigrams": len(
                {self.upper_trigram, self.lower_trigram}
                & {other.upper_trigram, other.lower_trigram}
            ),
        }


# ---------------------------------------------------------------------------
# 内部构造函数
# ---------------------------------------------------------------------------

def _trigram_from_lines(lines: tuple[int, int, int]) -> str:
    """从三爻序列（bottom,mid,top）反查八卦名。"""
    for name, data in TRIGRAMS.items():
        if data["lines"] == lines:
            return name
    raise ValueError(f"Unknown trigram lines: {lines}")


def _from_trigram_lines(
    upper_lines: tuple[int, int, int],
    lower_lines: tuple[int, int, int],
) -> HexArc:
    """从上下卦三爻序列构造 HexArc。"""
    upper_tri = _trigram_from_lines(upper_lines)
    lower_tri = _trigram_from_lines(lower_lines)
    for _seq_num, (name, ut, lt) in HEXAGRAM_SEQUENCE.items():
        if ut == upper_tri and lt == lower_tri:
            return HexArc(name=name)
    raise ValueError(
        f"No hexagram for upper={upper_tri} lower={lower_tri}"
    )


def _from_hex_lines(lines: tuple[int, ...]) -> HexArc:
    """从六爻序列（bottom→top）构造 HexArc。"""
    lower = (lines[0], lines[1], lines[2])
    upper = (lines[3], lines[4], lines[5])
    return _from_trigram_lines(upper, lower)


# ---------------------------------------------------------------------------
# Journey 级别的工具函数
# ---------------------------------------------------------------------------

def journey_transition_profile(
    waypoints: list[HexArc],
) -> dict:
    """给定一段 Journey 的 waypoint 序列，计算整体转移特征。"""
    if len(waypoints) < 2:
        return {"waypoint_count": len(waypoints), "transitions": []}

    transitions = []
    for i in range(1, len(waypoints)):
        prev, curr = waypoints[i - 1], waypoints[i]
        changed = prev.transitions_to(curr)
        transitions.append({
            "from": prev.name,
            "to": curr.name,
            "changed_lines": changed,
            "line_texts": {
                pos: curr.line_text(pos) or "(爻辞待补)"
                for pos in changed
            },
            "element_shift": prev.element_sequence_distance(curr),
            "correspondence_delta": (
                curr.correspondence_health - prev.correspondence_health
            ),
        })

    # 上卦五行序列
    upper_seq = [w.upper_element for w in waypoints]
    lower_seq = [w.lower_element for w in waypoints]

    return {
        "waypoint_count": len(waypoints),
        "transitions": transitions,
        "upper_element_sequence": upper_seq,
        "lower_element_sequence": lower_seq,
        "is_generation_flow": _is_generation_flow(upper_seq),
        "is_control_flow": _is_control_flow(upper_seq),
    }


def _is_generation_flow(elements: list[str]) -> bool:
    """检查五行序列是否沿着「生」的方向流动。"""
    gen_count = 0
    for i in range(1, len(elements)):
        if GENERATION.get(elements[i - 1]) == elements[i]:
            gen_count += 1
    return gen_count > len(elements) / 2


def _is_control_flow(elements: list[str]) -> bool:
    """检查五行序列是否沿着「克」的方向流动。"""
    ctrl_count = 0
    for i in range(1, len(elements)):
        if CONTROL.get(elements[i - 1]) == elements[i]:
            ctrl_count += 1
    return ctrl_count > len(elements) / 2


# ---------------------------------------------------------------------------
# 快速验证
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 基础验证
    tun = HexArc(name="屯")
    assert tun.upper_trigram == "坎"
    assert tun.lower_trigram == "震"
    assert tun.lines == (1, 0, 0, 0, 1, 0)
    assert tun.nuclear.name == "剥"
    assert tun.inverse.name == "鼎"
    assert tun.reverse.name == "蒙"

    # 爻变验证
    meng = HexArc(name="蒙")
    changed = tun.transitions_to(meng)
    assert sorted(changed) == [1, 2, 5, 6], f"Expected [1,2,5,6] got {changed}"

    # 五行验证
    assert tun.upper_element == "水"
    assert tun.lower_element == "木"
    # upper(水) 对 lower(木) 的关系：水生木，所以 upper 生 lower → "生"
    assert tun.internal_element_relation == "生"
    assert element_relation("水", "木") == "生"

    # 序卦邻接验证
    assert tun.wen_prev.name == "坤"
    assert tun.wen_next.name == "蒙"

    # 应关系验证：屯 = 1,0,0,0,1,0
    # 1↔4: 1,0 → 相应 ✓
    # 2↔5: 0,1 → 相应 ✓
    # 3↔6: 0,0 → 不应 ✗
    assert tun.correspondence_health == 2 / 3

    # Journey 转移特征
    journey = [HexArc("屯"), HexArc("革"), HexArc("渐")]
    profile = journey_transition_profile(journey)
    assert profile["waypoint_count"] == 3
    assert len(profile["transitions"]) == 2

    # 爻辞验证
    assert tun.line_text(1) == "磐桓，利居贞，利建侯"
    assert tun.line_text(6) == "乘马班如，泣血涟如"

    print("All assertions passed.")
