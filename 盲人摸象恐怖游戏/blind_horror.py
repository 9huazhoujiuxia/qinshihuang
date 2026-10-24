from ursina import *          # 第一行：Ursina 游戏引擎（安装：pip install ursina）
import random                 # 迷宫 DFS / 随机打墙 / 怪物游荡 / 脚步随机音调 / 环境音随机触发
import math                   # 角度、距离、抖动、晕影脉动与音效波形合成
import time as pytime         # 规格要求引入 time；别名避免覆盖 Ursina 自带 time（time.dt）
import os                     # 脚本目录 / 资源与音效文件管理
import shutil                 # 复制系统中文字体到游戏目录
import wave as _wave_mod      # 用代码合成 wav 音效（无外部素材也能出声）
import struct                 # wav 采样点打包
import urllib.request         # 尝试从网络直链下载音效与怪物 .obj 模型（全部 try-except 兜底）

# =====================================================================================
#  BLIND HORROR · 暗夜回声 —— 3D 第一人称"盲人"恐怖潜行游戏（防穿模·地面波纹版）
# -------------------------------------------------------------------------------------
#  ★ 本版核心：绝对不能出现穿墙透视 Bug
#    · 玩家/怪物/墙/保险丝/出口/石头 全部附加 BoxCollider（规格要求）
#    · 卡墙保护：实体中心陷入墙体时，每帧检测并强行推向最近的开阔地（地板格中心）
#    · 摄像机近平面前移（0.15）：贴墙时墙面不再被近裁剪面"切"掉导致看到墙后空洞
#    · 近距隐形线框平滑化：4 米内渐显暗灰线框（指数渐变 + 0.8 米滞回带），
#      移动时绝不闪烁
#  回声探测强化（参考《第五人格》盲女）：
#    · 右键敲击：膨胀线框球体 + ★地面发光青色线框圆环（贴地迅速扩大并淡出的
#      声呐涟漪，双环错峰）+ 小地图快照
#    · 波纹扫过的墙/怪物：wireframe=True + 高亮青白色 rgba(0,255,255,200)，
#      持续 1.5 秒——黑暗中清晰记住这一瞬间的迷宫路线
#  恐怖氛围：
#    · BGM(bgm_horror.mp3) + 风声(wind_ambient.mp3) 循环；随机滴水/金属碰撞环境音
#    · 怪物 PATROL→CHASE 切换播放 monster_scream.mp3 嘶吼；动态心跳（音量+频率）
#    · 怪物逼近：屏幕边缘暗红晕影（不遮挡中心视野）+ 镜头微颤（恐惧发抖）
#  玩法：40x40 DFS 大迷宫（含打墙环路）→ 收集 3 枚保险丝（近距黄光脉动+电流声）
#    → 出口绿光亮起 → 触门通关。3 条命：突脸扣命，重生保留保险丝，命尽 GAME OVER。
#
#  资源规范（★ 优先在游戏同目录寻找，缺失时安全降级，绝不闪退）：
#    音效：bgm_horror.mp3 / wind_ambient.mp3 / monster_scream.mp3 /
#          heartbeat.wav / jumpscare.mp3 / step_walk.wav
#    模型：monster.obj（失败则代码拼凑：黑色细长身体+头+双臂+红眼）
#    找不到时自动使用 sounds/ 目录的代码合成音效，或 print 文字音效占位。
#
#  键位：WASD 移动 | Shift 奔跑(×1.8·耗体·巨响) | 左键按住潜行(半速·无声·回体)
#        右键回声(CD4s·耗10体·地面波纹+小地图) | F 投石诱饵 | E 收集保险丝
#        Tab 技能面板(暂停+解锁鼠标) | Esc 暂停
#
#  状态机 game_state（6 态）：'MENU' | 'PLAYING' | 'PAUSED' | 'SKILL_SELECT' | 'DEAD' | 'WIN'
#
#  防闪退铁律（贯穿全文件）：
#    1) 所有实体 update() 第一行：if game_state != GameState.PLAYING: return
#    2) 遍历实体列表一律 for obj in list(target_list): 浅拷贝
#    3) 销毁顺序：is_dead=True → 判定中过滤 → 从列表 remove() → destroy()
#    4) 一切资源加载（文件/网络）全部 try-except + 超时，失败静默降级
#
#  运行：  pip install ursina  →  python blind_horror.py
# =====================================================================================


# ★ Ursina 应用必须先于任何实体创建（文末 app.run() 启动主循环）
app = Ursina(title='BLIND HORROR · 暗夜回声')

# ----------------------------- 摄像机近裁剪面优化（防穿墙透视） -----------------------------
# 默认近平面较远（1.0）：人贴墙时墙面比近平面更近会被裁掉，直接看到墙后空洞。
# 把近平面前移到 0.15：贴脸的墙面照常渲染，配合卡墙保护彻底消除"穿墙看到空洞"。
try:
    base.camLens.set_near(0.15)
    base.camLens.set_far(600.0)
except Exception:
    pass                        # 个别版本镜头接口不同：保持默认，不影响运行

# ----------------------------- 核心环境：极暗氛围（非纯黑） -----------------------------
window.color = color.rgb(10, 10, 10)     # 全局极暗底色（规格要求，不使用纯黑）
scene.fog_color = color.rgb(10, 10, 10)  # 雾色与底色一致：远处物体模糊溶入黑暗（浓雾）
scene.fog_density = 0.08                 # 雾密度

# 环境光：极弱（20,20,20），配合点光让"贴脸"的物体有最低限度的可见度
try:
    ambient_light = AmbientLight(color=color.rgba(20, 20, 20, 255))
except Exception:
    ambient_light = None                 # 个别 Ursina 版本光照接口不同：静默降级

# lit shader：让墙体/地面真正响应环境光与点光源（否则光源不生效）。
# 多路径安全导入，全部失败则退化为无光照渲染（游戏依旧可玩，只是没有微光视野）。
lit_shader = None
for _imp in (
        lambda: __import__('ursina.shaders.lit_shader', fromlist=['lit_shader']).lit_shader,
        lambda: __import__('ursina.shaders', fromlist=['lit_shader']).lit_shader,
        lambda: __import__('ursina').lit_shader):
    try:
        lit_shader = _imp()
        break
    except Exception:
        continue

try:
    window.fps_counter.enabled = False   # 关闭 FPS 显示，保持画面纯净
    window.exit_button.enabled = False   # 关闭右上角退出按钮（用主菜单"退出游戏"）
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))    # 脚本目录（资源/字体/音效）
SOUND_DIR = os.path.join(SCRIPT_DIR, 'sounds')             # 合成/下载音效目录
MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')             # 下载模型目录


def setup_cjk_font():
    """★ 本机 Panda3D 无法通过 'C:/Windows/Fonts/...' 绝对路径加载字体（会显示为方块）。
    实测可靠方案：把系统中文字体复制到游戏目录，用相对文件名加载。
    找不到则静默回退默认字体（英文正常，不影响运行）。"""
    for name in ('simhei.ttf', 'msyh.ttc', 'wqy-microhei.ttc', 'PingFang.ttc'):
        if os.path.exists(os.path.join(SCRIPT_DIR, name)):
            try:
                Text.default_font = name
                return name
            except Exception:
                pass
    for src in ('C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/msyh.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                '/System/Library/Fonts/PingFang.ttc'):
        if not os.path.exists(src):
            continue
        try:
            shutil.copy2(src, SCRIPT_DIR)
            Text.default_font = os.path.basename(src)
            return os.path.basename(src)
        except Exception:
            continue
    return None


setup_cjk_font()

# =====================================================================================
#  一、全局状态机与数值策划表
# =====================================================================================
class GameState:
    """游戏全局状态机（6 态）。所有实体 update() 以 PLAYING 判定作为第一行闸门。"""
    MENU = 'MENU'                  # 主菜单
    PLAYING = 'PLAYING'            # 游玩中（唯一执行游戏逻辑的状态）
    PAUSED = 'PAUSED'              # 暂停
    SKILL_SELECT = 'SKILL_SELECT'  # 局内技能面板（Tab 呼出）
    DEAD = 'DEAD'                  # 3 条命耗尽 → GAME OVER
    WIN = 'WIN'                    # 通关


game_state = GameState.MENU        # ★ 全局状态（所有 update 的总闸门）

# ---------------- 迷宫（40x40 大地图）----------------
GRID_N = 40                 # 迷宫二维数组尺寸：40x40（0=路，1=墙）→ 19x19 个房间
BRAID_RATIO = 0.18          # 完美迷宫生成后随机打墙比例：制造死胡同环路与十字路口
TILE = 4.0                  # 每个地块的世界尺寸（米）→ 整图 160x160 米
WALL_HEIGHT = 4.0           # 墙高（墙方块 4x4x4）

# ---------------- 玩家移动与体力 ----------------
WALK_SPEED = 4.5            # WASD 基础速度
RUN_MULT = 1.8              # Shift 奔跑倍率（4.5×1.8=8.1，快于怪物冲刺 7.5）
SNEAK_MULT = 0.5            # 鼠标左键按住潜行：速度减半
STAND_HEIGHT = 1.8          # 视点高度
PLAYER_RADIUS = 0.5         # 玩家碰撞半径（自定义 AABB 推出解算用）
BASE_MAX_STAMINA = 100.0    # 体力上限
RUN_DRAIN_PER_FRAME = 0.5   # 奔跑每帧消耗体力 0.5（×60×dt 帧率无关化）
REGEN_NORMAL = 10.0         # 普通状态每秒回体
REGEN_SNEAK = 18.0          # 潜行（按住左键）时体力恢复最快
WALK_NOISE = 10.0           # 步行噪音半径
RUN_NOISE = 20.0            # 奔跑"巨大噪音"半径
ALL_MONSTERS = 1.0e9        # 广播给所有怪物（回声敲击/石头落地）

# ---------------- 生命 / 回声 / 投掷 / 收集 ----------------
START_LIVES = 3             # 初始生命条数（★ 3 条命系统）
ECHO_COOLDOWN = 4.0         # 鼠标右键敲击冷却（秒）
ECHO_STAMINA_COST = 10.0    # 敲击消耗体力
ECHO_DURATION = 1.5         # 线框球 1.5 秒膨胀完毕
ECHO_MAX_RADIUS = 30.0      # 回声最大半径（雷达强化后 ×1.5 = 45）
ECHO_MAX_SCALE = 60.0       # 线框球最终 scale（直径 60 = 半径 30）
REVEAL_RESTORE_DELAY = 1.5  # ★ 高亮持续 1.5 秒后恢复（规格要求，青白色可视窗口）
STONE_SPEED = 16.0          # 石头水平飞行速度（1.5 秒约 24 米）
STONE_LIFE = 1.5            # 石头飞行 1.5 秒后落地
STONE_GRAVITY = 1.5         # 轻微下坠弧线
STONE_COOLDOWN = 3.0        # 扔石头冷却
FUSES_NEEDED = 3            # 通关需要收集的保险丝数量

# ---------------- 怪物 / 突脸 / 危险反馈 ----------------
KILL_DISTANCE = 1.2         # 距离 < 1.2 → 突脸 + 扣命
MONSTER_COUNT = 3           # 40x40 大迷宫中盘踞的怪物数量
MONSTER_CHASE_SPEED = 7.5   # 怪物冲刺速度（1.5 倍速：玩家基础 4.5 × 1.5）
MONSTER_PATROL_SPEED = 1.6  # 怪物巡逻速度
MONSTER_AUDIO_RANGE = 8.0   # 怪物近距音效（心跳/重步）触发距离
DANGER_RANGE = 10.0         # 距离 < 10 → 晕影渐显 + 恐惧发抖
SCARE_DURATION = 0.7        # 突脸动画时长（相机剧烈抖动）
SCARE_DIST = 0.5            # 突脸时怪物瞬移到相机正前方 0.5 米（规格值）

# ---------------- 被动感知（墙体线框 / 保险丝微光）----------------
WALL_SENSE_ENTER = 4.0      # 玩家 4 米内：墙渐显暗灰线框（进入阈值）
WALL_SENSE_EXIT = 4.8       # ★ 滞回带：超过 4.8 米才渐隐——边界来回走动不闪烁
FUSE_SENSE_RANGE = 10.0     # 保险丝 10 米内脉动闪烁 + 电流滋滋声

# ---------------- 小地图 ----------------
MINIMAP_VIEW = 20.0         # 小地图覆盖玩家周围 20 米
MINIMAP_MARK_RANGE = 20.0   # 保险丝/怪物亮点显示范围
MINIMAP_SIZE = 0.34         # 小地图边长（UI 尺寸）
MINIMAP_CELL_POOL = 130     # 墙体格子对象池

# ---------------- 局内技能 ----------------
SKILL_COST = 30.0           # 技能激活消耗体力（每局各一次）
SKILLS = {
    'radar':  {'name': '雷达强化', 'desc': '回声范围 30 → 45（本局生效）'},
    'silent': {'name': '静步大师', 'desc': '移动不再发出任何噪音（本局生效）'},
}

# ---------------- 运行期全局数据 ----------------
player_lives = START_LIVES  # ★ 生命条数（规格要求的全局变量名）
collected_fuses = 0         # ★ 已收集保险丝数量（规格要求的全局变量名）
player = None               # 玩家实体（由 LevelManager 创建）
level_manager = None        # 关卡管理器（文件末尾创建）
scare_active = False        # 突脸动画进行中（冻结输入/怪物，只驱动抖动）
scare_timer = 0.0           # 突脸剩余时间
danger_k = 0.0              # 最近怪物的危险强度（0~1）：驱动晕影/发抖/心跳
monster_step_timer = 0.0    # 怪物近距重步的触发节拍
buzz_timer = 0.0            # 保险丝电流滋滋声的触发节拍
ambient_event_timer = 8.0   # 随机环境音（滴水/金属碰撞）的触发倒计时

WALLS = []                  # 当前关卡所有墙体
MONSTERS = []               # 当前关卡所有怪物
FUSES = []                  # 当前所有未收集的保险丝
STONES = []                 # 飞行中的石头
ECHO_SPHERES = []           # 存活中的回声线框球
RIPPLES = []                # 存活中的地面声呐波纹（★ 本版新增）

# =====================================================================================
#  二、音效系统：同目录规格资源 → sounds/ 合成或下载 → print 占位，三级回退
# =====================================================================================
# ★ 规格指定的同目录资源文件名（优先加载；缺失时安全降级，绝不闪退）
RESOURCE_FILES = {
    'bgm':       'bgm_horror.mp3',
    'wind':      'wind_ambient.mp3',
    'roar':      'monster_scream.mp3',
    'heartbeat': 'heartbeat.wav',
    'jumpscare': 'jumpscare.mp3',
    'step':      'step_walk.wav',
}

# sounds/ 目录下的合成/下载文件名（代码合成兜底，保证零素材也能完整出声）
SOUND_FILES = {
    'bgm':          'bgm.wav',          # 恐怖 BGM：不和谐低频轰鸣（循环）
    'wind':         'wind.wav',         # 持续的风声（循环）
    'breath':       'breath.wav',       # 玩家平缓呼吸声（循环）
    'drip':         'drip.wav',         # 随机环境音：滴水声
    'clang':        'clang.wav',        # 随机环境音：远处金属碰撞
    'buzz':         'buzz.wav',         # 保险丝电流滋滋声
    'step':         'step.wav',         # 行走脚步（随机音调）
    'step_run':     'step_run.wav',     # 奔跑急促脚步
    'sonar':        'sonar.wav',        # 敲击/回声：清脆的"滴"声呐
    'heartbeat':    'heartbeat.wav',    # 心跳（循环，音量与频率随怪物距离）
    'monster_step': 'monster_step.wav', # 怪物靠近：沉重脚步
    'mbreath':      'mbreath.wav',      # 怪物沉重喘息
    'roar':         'roar.wav',         # 怪物追击嘶吼（PATROL→CHASE 切换时）
    'skill':        'skill.wav',        # 技能激活
    'jumpscare':    'jumpscare.wav',    # 突脸：高频刺耳恐怖音
}

# 网络直链（公共音效库示例；★ 链接可能失效或需跳转——urllib 下载带超时与 try-except，
# 失败自动回退到代码合成音效，绝不会闪退）。
SOUND_URLS = {
    'bgm':          'https://assets.mixkit.co/active_storage/sfx/2434/2434-preview.mp3',
    'wind':         'https://assets.mixkit.co/active_storage/sfx/2382/2382-preview.mp3',
    'breath':       'https://assets.mixkit.co/active_storage/sfx/2564/2564-preview.mp3',
    'drip':         'https://assets.mixkit.co/active_storage/sfx/1789/1789-preview.mp3',
    'clang':        'https://assets.mixkit.co/active_storage/sfx/1723/1723-preview.mp3',
    'buzz':         'https://assets.mixkit.co/active_storage/sfx/2567/2567-preview.mp3',
    'step':         'https://assets.mixkit.co/active_storage/sfx/2167/2167-preview.mp3',
    'step_run':     'https://assets.mixkit.co/active_storage/sfx/2168/2168-preview.mp3',
    'sonar':        'https://assets.mixkit.co/active_storage/sfx/1867/1867-preview.mp3',
    'heartbeat':    'https://assets.mixkit.co/active_storage/sfx/2076/2076-preview.mp3',
    'monster_step': 'https://assets.mixkit.co/active_storage/sfx/2977/2977-preview.mp3',
    'mbreath':      'https://assets.mixkit.co/active_storage/sfx/2564/2564-preview.mp3',
    'roar':         'https://assets.mixkit.co/active_storage/sfx/2975/2975-preview.mp3',
    'skill':        'https://assets.mixkit.co/active_storage/sfx/2567/2567-preview.mp3',
    'jumpscare':    'https://assets.mixkit.co/active_storage/sfx/2975/2975-preview.mp3',
}


def try_download_sounds():
    """尝试用 urllib.request 从网络直链下载音效到 sounds/（每个 5 秒超时）。
    ★ 按文件头校验格式：RIFF 头才存为 .wav；mp3 等其他格式存为 .mp3
    （load_audio 会依次尝试 wav → mp3）。任何失败静默跳过（代码合成兜底）。"""
    try:
        os.makedirs(SOUND_DIR, exist_ok=True)
    except Exception:
        return
    for name, url in SOUND_URLS.items():
        dest = os.path.join(SOUND_DIR, SOUND_FILES[name])
        if os.path.exists(dest) or os.path.exists(os.path.join(SOUND_DIR, name + '.mp3')):
            continue                       # 已有本地音效（下载或合成过）则跳过
        tmp = dest + '.tmp'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp, open(tmp, 'wb') as f:
                f.write(resp.read(2 * 1024 * 1024))    # 最多 2MB
            if os.path.getsize(tmp) > 20 * 1024:       # 太小的多半是错误页
                with open(tmp, 'rb') as hf:
                    head = hf.read(4)
                if head == b'RIFF':                    # 真 wav
                    os.replace(tmp, dest)
                    print(f'（已下载网络音效：{name}.wav）')
                else:                                   # mp3 等其他格式，按真实扩展名保存
                    os.replace(tmp, os.path.join(SOUND_DIR, name + '.mp3'))
                    print(f'（已下载网络音效：{name}.mp3）')
            else:
                os.remove(tmp)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass


_WAV_RATE = 22050            # 合成音效采样率


def _write_wav(path, sample_func, duration, volume=1.0):
    """把采样函数合成为 16bit 单声道 wav 文件（纯代码生成，无外部素材）"""
    n = int(_WAV_RATE * duration)
    dt = 1.0 / _WAV_RATE
    frames = bytearray()
    for i in range(n):
        t = i * dt
        s = max(-1.0, min(1.0, sample_func(t, dt) * volume))
        frames += struct.pack('<h', int(s * 32000))
    with _wave_mod.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_WAV_RATE)
        w.writeframes(bytes(frames))


def ensure_sound_assets():
    """首次运行时用代码合成全部缺失音效到 sounds/（已存在则跳过）。
    任何一条失败只影响该音效（自动回退 print 占位），不影响游戏运行。"""
    try:
        os.makedirs(SOUND_DIR, exist_ok=True)
        specs = {}

        # 1) 恐怖 BGM：40/41.5Hz 拍频轰鸣 + 次声 30Hz + 61Hz + 662Hz 诡异颤音
        #    （各频率×时长均为整数周期 → 6 秒无缝循环；tanh 软限幅出浑浊质感）
        def _bgm(t, dt):
            s = (0.5 * math.sin(2 * math.pi * 40 * t)
                 + 0.45 * math.sin(2 * math.pi * 41.5 * t)
                 + 0.3 * math.sin(2 * math.pi * 30 * t)
                 + 0.22 * math.sin(2 * math.pi * 61 * t)
                 + 0.05 * math.sin(2 * math.pi * 662 * t)
                 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 2.0)))
            return math.tanh(s * 1.5) * 0.5

        specs['bgm.wav'] = (_bgm, 6.0, 0.45)

        # 2) 持续风声：一阶低通噪声 + 4 秒周期慢速起伏包络（无缝循环）
        wind_lp = [0.0]

        def _wind(t, dt):
            wind_lp[0] += 0.08 * ((random.random() * 2 - 1) - wind_lp[0])
            return wind_lp[0] * (0.55 + 0.45 * math.sin(2 * math.pi * t / 4.0)) * 1.2

        specs['wind.wav'] = (_wind, 4.0, 0.50)

        # 3) 玩家呼吸声：4 秒一个呼吸循环（吸气渐强 1.7s → 呼气渐弱 2.3s）
        breath_lp = [0.0]

        def _breath(t, dt):
            breath_lp[0] += 0.2 * ((random.random() * 2 - 1) - breath_lp[0])
            if t < 1.7:
                env = (t / 1.7) ** 1.5 * 0.8
            else:
                env = max(0.0, 1.0 - (t - 1.7) / 2.3) ** 1.5 * 0.6
            return breath_lp[0] * env * 1.4

        specs['breath.wav'] = (_breath, 4.0, 0.55)

        # 4) 滴水声：950→600Hz 快速下滑的水滴 + 0.1 秒后的轻微回声
        def _drip(t, dt):
            s = math.sin(2 * math.pi * (950 - 350 * min(t * 12, 1)) * t) \
                * math.exp(-t * 55)
            if 0.10 <= t < 0.16:
                s += 0.4 * math.sin(2 * math.pi * 900 * (t - 0.10)) \
                    * math.exp(-(t - 0.10) * 55)
            return s

        specs['drip.wav'] = (_drip, 0.22, 0.5)

        # 5) 远处金属碰撞：非谐和泛音（523/1337/2117Hz）长余音 + 起振噪声
        def _clang(t, dt):
            s = (0.5 * math.sin(2 * math.pi * 523 * t)
                 + 0.35 * math.sin(2 * math.pi * 1337 * t)
                 + 0.25 * math.sin(2 * math.pi * 2117 * t)
                 + 0.2 * (random.random() * 2 - 1) * math.exp(-t * 90))
            return s * math.exp(-t * 7)

        specs['clang.wav'] = (_clang, 0.7, 0.35)

        # 6) 保险丝电流滋滋声：47Hz 门控噪声（噼啪的电气质感）
        def _buzz(t, dt):
            gate = 1.0 if math.sin(2 * math.pi * 47 * t) >= 0 else 0.2
            return (random.random() * 2 - 1) * gate * math.exp(-t * 14)

        specs['buzz.wav'] = (_buzz, 0.18, 0.4)

        # 7) 行走脚步：短促噪声 + 95Hz 轻叩，快速衰减
        specs['step.wav'] = (
            lambda t, dt: (0.6 * math.sin(2 * math.pi * 95 * t)
                           + 0.5 * (random.random() * 2 - 1)) * math.exp(-t * 45),
            0.09, 0.55)

        # 8) 奔跑脚步：更低沉更响的 70Hz 重踏
        specs['step_run.wav'] = (
            lambda t, dt: (0.9 * math.sin(2 * math.pi * 70 * t)
                           + 0.6 * (random.random() * 2 - 1)) * math.exp(-t * 28),
            0.13, 0.80)

        # 9) 声呐敲击：1200→450Hz 线性扫频正弦（相位累积实现扫频）
        sonar_phase = [0.0]

        def _sonar(t, dt):
            f = 1200.0 - 750.0 * (t / 0.6)
            sonar_phase[0] += 2 * math.pi * f * dt
            return math.sin(sonar_phase[0]) * math.exp(-t * 3.5)

        specs['sonar.wav'] = (_sonar, 0.6, 0.60)

        # 10) 心跳：两记 52Hz 低频闷响（"咚—咚"），循环；节律由 pitch 动态调节
        def _heartbeat(t, dt):
            s = 0.0
            for t0, amp in ((0.05, 1.0), (0.32, 0.72)):
                u = t - t0
                if 0.0 <= u < 0.22:
                    s += math.sin(2 * math.pi * 52 * u) * math.exp(-u * 16) * amp
            return s

        specs['heartbeat.wav'] = (_heartbeat, 0.7, 0.85)

        # 11) 怪物沉重脚步：42Hz 重击 + 噪声
        specs['monster_step.wav'] = (
            lambda t, dt: (0.9 * math.sin(2 * math.pi * 42 * t)
                           + 0.35 * (random.random() * 2 - 1)) * math.exp(-t * 16),
            0.16, 0.80)

        # 12) 怪物沉重喘息：55Hz 喉音 + 低通噪声呼气包络
        mbreath_lp = [0.0]

        def _mbreath(t, dt):
            mbreath_lp[0] += 0.12 * ((random.random() * 2 - 1) - mbreath_lp[0])
            env = min(t * 8, 1.0) * max(0.0, 1.0 - (t - 0.35) / 0.45)
            return (mbreath_lp[0] * 0.8
                    + 0.5 * math.sin(2 * math.pi * 55 * t)) * env

        specs['mbreath.wav'] = (_mbreath, 0.8, 0.6)

        # 13) 追击嘶吼（Roar）：300→90Hz 下坠锯齿 + 16Hz 怒颤噪声 + 1200Hz 穿透尖啸，
        #     tanh 失真压缩——极具穿透力的震慑吼叫
        def _roar(t, dt):
            f = 300.0 - 210.0 * (t / 0.9)
            saw = 2.0 * ((f * t) % 1.0) - 1.0
            trem = 0.6 + 0.4 * math.sin(2 * math.pi * 16 * t)
            squeal = 0.3 * math.sin(2 * math.pi * 1200 * (1.0 - t * 0.8) * t)
            s = 0.55 * saw + 0.4 * (random.random() * 2 - 1) * trem + squeal
            env = min(t * 25, 1.0) * math.exp(-t * 2.2)
            return math.tanh(s * 2.5) * env

        specs['roar.wav'] = (_roar, 0.9, 0.9)

        # 14) 技能音：660→990Hz 双音上行风铃
        def _skill(t, dt):
            if t < 0.15:
                return math.sin(2 * math.pi * 660 * t) * math.exp(-t * 18)
            u = t - 0.15
            return 0.8 * math.sin(2 * math.pi * 990 * u) * math.exp(-u * 14)

        specs['skill.wav'] = (_skill, 0.35, 0.55)

        # 15) 突脸尖叫：1900Hz 振颤方波 + 2800→500Hz 下坠扫频 + 噪声，刺耳高频
        screech_phase = [0.0]

        def _jumpscare(t, dt):
            vib = 1.0 + 0.06 * math.sin(2 * math.pi * 11 * t)
            square = 1.0 if math.sin(2 * math.pi * 1900 * vib * t) >= 0 else -1.0
            f = 2800.0 - 2300.0 * (t / 1.3)
            screech_phase[0] += 2 * math.pi * f * dt
            noise = random.random() * 2 - 1
            env = min(t * 30.0, 1.0) * math.exp(-t * 0.8)
            return (0.55 * square + 0.45 * math.sin(screech_phase[0]) + 0.35 * noise) * env

        specs['jumpscare.wav'] = (_jumpscare, 1.3, 0.95)

        for filename, (func, dur, vol) in specs.items():
            path = os.path.join(SOUND_DIR, filename)
            if not os.path.exists(path):
                _write_wav(path, func, dur, vol)
        return True
    except Exception as e:
        print(f'（音效合成失败，将使用文字音效占位：{e}）')
        return False


def load_audio(name, loop=False, volume=1.0):
    """★ 音效加载三级回退（资源规范，绝不闪退）：
    ① 游戏同目录的规格资源文件（bgm_horror.mp3 等）
    ② sounds/ 目录下代码合成/网络下载的 .wav / .mp3
    ③ 全部失败 → 返回 None（播放时 print 文字占位）"""
    candidates = []
    res = RESOURCE_FILES.get(name)
    if res:
        candidates.append(os.path.join(SCRIPT_DIR, res))          # 同目录规格文件
    local = os.path.join(SOUND_DIR, SOUND_FILES.get(name, ''))
    if local:
        candidates.append(local)                                   # 合成 wav
    candidates.append(os.path.join(SOUND_DIR, name + '.mp3'))      # 下载 mp3
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return Audio(path, loop=loop, volume=volume, autoplay=False)
            except Exception:
                continue
    return None


try_download_sounds()         # 先尝试网络直链（失败静默跳过）
ensure_sound_assets()         # 缺失的用代码合成补齐

# 常驻循环音：恐怖 BGM + 风声 + 玩家呼吸 + 心跳（音量/频率随怪物距离动态调节）
bgm_audio = load_audio('bgm', loop=True, volume=0.32)
wind_audio = load_audio('wind', loop=True, volume=0.30)
breath_audio = load_audio('breath', loop=True, volume=0.35)
heartbeat_audio = load_audio('heartbeat', loop=True, volume=0.0)
_one_shot_cache = {}          # 单次播放音效的缓存（复用 Audio 对象，改 pitch/volume）

SOUND_TEXT = {
    'bgm':          '【BGM】嗡————（低沉不和谐的轰鸣萦绕）',
    'wind':         '【环境】呼——风声掠过墓道',
    'breath':       '（呼吸……呼吸……）',
    'drip':         '（嗒……水滴坠落）',
    'clang':        '（哐————远处传来金属的哀鸣）',
    'buzz':         '（滋……滋……电流微响）',
    'step':         '（嗒……）',
    'step_run':     '（咚！咚！——狂奔的脚步炸响）',
    'sonar':        '【回声】滴————（声呐般的敲击扩散开来）',
    'heartbeat':    '（咚、咚……心跳）',
    'monster_step': '（咚——咚——沉重的怪物脚步）',
    'mbreath':      '【怪物】呼——嘶——（沉重的喘息）',
    'roar':         '【怪物嘶吼】呃 啊 啊 啊 ——！！！',
    'skill':        '【技能】嗡——（能力觉醒）',
    'jumpscare':    '【尖叫】呃啊啊啊啊啊——！！！',
}


def play_sfx(name, volume=1.0, pitch=None):
    """播放一次性音效：Audio → 失败则 print 占位。
    脚步类音效传入随机 pitch 实现音调变化。"""
    if name not in _one_shot_cache:
        _one_shot_cache[name] = load_audio(name)
    audio = _one_shot_cache[name]
    if audio is None:
        print(SOUND_TEXT.get(name, f'（音效：{name}）'))
        return
    try:
        if pitch is not None:
            audio.pitch = pitch
        audio.volume = volume
        audio.play()
    except Exception:
        print(SOUND_TEXT.get(name, f'（音效：{name}）'))


# =====================================================================================
#  三、怪物模型：同目录 monster.obj → models/monster.obj → 网络下载 → 组合人形兜底
# =====================================================================================
# 网络直链示例（three.js 官方示例仓库）；下载失败/读取失败自动回退组合模型
MONSTER_OBJ_URL = ('https://raw.githubusercontent.com/mrdoob/three.js/dev/'
                   'examples/models/obj/male02/male02.obj')


def try_download_monster_model():
    """用 urllib.request 尝试下载 .obj 模型（6 秒超时）。
    成功返回本地路径，失败返回 None（组合模型兜底）。"""
    dest = os.path.join(MODEL_DIR, 'monster.obj')
    if os.path.exists(dest):
        return dest
    tmp = dest + '.tmp'
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        req = urllib.request.Request(MONSTER_OBJ_URL,
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as resp, open(tmp, 'wb') as f:
            f.write(resp.read(8 * 1024 * 1024))       # 最多 8MB
        if os.path.getsize(tmp) > 50 * 1024:
            os.replace(tmp, dest)
            print('（已下载网络怪物模型 monster.obj）')
            return dest
        os.remove(tmp)
        return None
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


def find_monster_model():
    """★ 资源规范：① 游戏同目录 monster.obj（规格资源）→ ② models/monster.obj
    （此前网络下载缓存）→ ③ 现在尝试网络下载 → ④ None（代码拼凑组合模型）。"""
    for path in (os.path.join(SCRIPT_DIR, 'monster.obj'),
                 os.path.join(MODEL_DIR, 'monster.obj')):
        if os.path.exists(path):
            return path
    return try_download_monster_model()


MONSTER_OBJ_PATH = find_monster_model()

# =====================================================================================
#  四、通用工具（距离 / 安全销毁 / 噪音广播 / 碰撞 / 卡墙保护 / 线框 / 光照）
# =====================================================================================
def dist_xz(a, b):
    """计算两个位置在水平面（XZ）上的距离"""
    return math.hypot(a.x - b.x, a.z - b.z)


def add_box_collider(entity, center=None, size=None):
    """★ 规格要求：给实体附加 Box 碰撞体（collider='box' 等价）。
    显式指定 center/size（不依赖模型包围盒，模型缺失的根实体也安全）；
    try-except 包裹——任何版本差异都不允许闪退。"""
    try:
        entity.collider = BoxCollider(entity, center=center or Vec3(0, 0, 0),
                                      size=size or Vec3(1, 1, 1))
    except Exception:
        entity.collider = None


def safe_destroy(entity):
    """★ 销毁铁律：先 is_dead=True → 从所有追踪列表 remove() → destroy()。
    所有交互判定都过滤 is_dead 实体，杜绝销毁后仍被访问导致的闪退。"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    entity.is_dead = True
    for lst in (WALLS, MONSTERS, FUSES, STONES, ECHO_SPHERES, RIPPLES):
        if entity in lst:
            lst.remove(entity)
    destroy(entity)


def emit_noise(position, radius):
    """噪音事件广播：radius 为可听半径（ALL_MONSTERS 表示广播给所有怪物）。"""
    for m in list(MONSTERS):                    # ★ 浅拷贝遍历
        if getattr(m, 'is_dead', False):
            continue
        m.hear_noise(position, radius)


def resolve_collisions(entity, radius):
    """圆形实体 vs 轴对齐墙体（AABB）碰撞修正：把实体推出墙体，防止穿墙。
    大迷宫墙块近千个，先用包围盒快速剔除远处的墙块，只对紧邻地块做精确判定。"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    reach = TILE + radius                       # 只可能撞上紧邻地块的墙
    for wall in list(WALLS):                    # ★ 浅拷贝遍历墙体列表
        if wall.is_dead:
            continue                            # ★ 过滤已死亡实体
        if abs(wall.x - entity.x) > reach or abs(wall.z - entity.z) > reach:
            continue                            # 快速剔除：距离过远不可能相撞
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        nearest_x = clamp(entity.x, wall.x - hx, wall.x + hx)
        nearest_z = clamp(entity.z, wall.z - hz, wall.z + hz)
        dx = entity.x - nearest_x
        dz = entity.z - nearest_z
        dist_sq = dx * dx + dz * dz
        if dist_sq >= radius * radius:
            continue                            # 没碰到这面墙
        if dist_sq <= 1e-9:
            overlap_x = hx - abs(entity.x - wall.x)
            overlap_z = hz - abs(entity.z - wall.z)
            if overlap_x <= overlap_z:
                entity.x = wall.x + (hx + radius) * (1 if entity.x >= wall.x else -1)
            else:
                entity.z = wall.z + (hz + radius) * (1 if entity.z >= wall.z else -1)
        else:
            dist = math.sqrt(dist_sq)
            push = radius - dist                # 需要推出的深度
            entity.x += dx / dist * push
            entity.z += dz / dist * push


def push_out_if_stuck(entity):
    """★ 卡墙保护（规格要求）：若实体中心陷入某面墙的 AABB 内部（穿模），
    立即强行传送到最近的开阔地（地板地块中心）——保证任何情况下都不会卡在墙里。"""
    if entity is None or getattr(entity, 'is_dead', False):
        return False
    for wall in list(WALLS):                    # ★ 浅拷贝遍历
        if wall.is_dead:
            continue
        if abs(wall.x - entity.x) > TILE or abs(wall.z - entity.z) > TILE:
            continue
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        if abs(entity.x - wall.x) < hx and abs(entity.z - wall.z) < hz:
            # 中心确实在墙内：推向最近的开阔地（地板格中心）
            tile = level_manager.nearest_floor_tile(entity.position)
            world = level_manager.tile_to_world(tile)
            entity.x = world.x
            entity.z = world.z
            return True
    return False


def set_wireframe(entity, on):
    """把实体渲染模式切换为线框/实心（规格中的 wireframe 属性）。
    ursina 5.2 的 Entity 没有原生 wireframe 属性——先按规格设置同名属性（无害占位），
    再调用底层 Panda3D 接口真正生效；全部 try-except，任何版本不兼容都不崩溃。"""
    try:
        entity.wireframe = on                   # 规格要求的属性写法
    except Exception:
        pass
    try:
        if on:
            entity.set_render_mode_wireframe(2)
        else:
            entity.set_render_mode_filled(2)    # 同优先级恢复实心
    except Exception:
        pass


def apply_lit_shader(entity):
    """给实体挂载 lit shader（有光照时墙体/地面才会响应点光与环境光）。
    lit_shader 不可用时静默跳过（退化为无光照渲染，不影响可玩性）。"""
    if lit_shader is not None:
        try:
            entity.shader = lit_shader
        except Exception:
            pass


def clear_shader(entity):
    """清除 shader（恢复默认无光照渲染——用于发光实体/线框高亮，保证亮度不被灯光压暗）"""
    try:
        entity.shader = None
    except Exception:
        pass


# =====================================================================================
#  五、迷宫生成：DFS 递归回溯 + 随机打墙（40x40 二维数组，0=路，1=墙）
# =====================================================================================
def generate_maze_grid():
    """用递归回溯法（DFS 深度优先 + 回溯）生成 40x40 的二维数组迷宫：
    19x19 个房间（奇数索引 1,3,…,37），两房间之间的墙块被打通。
    随后按 BRAID_RATIO 随机打掉一部分"非边界墙壁"——制造死胡同环路与十字路口，
    避免玩家只有一条单行道（规格要求）。"""
    grid = [[1] * GRID_N for _ in range(GRID_N)]     # 先全部置 1（墙）
    max_odd = GRID_N - 3                             # 奇数索引最大值 37
    grid[1][1] = 0                                   # 从网格 (0,0) 角的房间开始挖
    stack = [(1, 1)]
    while stack:
        x, z = stack[-1]
        neighbors = []                               # 未挖通的相邻房间（间隔 2 格）
        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, nz = x + dx, z + dz
            if 1 <= nx <= max_odd and 1 <= nz <= max_odd and grid[nz][nx] == 1:
                neighbors.append((nx, nz))
        if neighbors:
            nx, nz = random.choice(neighbors)
            grid[z + (nz - z) // 2][x + (nx - x) // 2] = 0   # 打通中间的墙
            grid[nz][nx] = 0                                 # 挖开目标房间
            stack.append((nx, nz))
        else:
            stack.pop()                           # 无路可挖，回溯
    # ---- ★ 增加路线：随机打通一部分非边界墙壁（只打开"恰好隔开两条走廊"的墙，
    # 既生成环路，又保持迷宫结构）----
    opened = 0
    for z in range(1, GRID_N - 1):                # 范围排除边界 → 非边界墙壁
        for x in range(1, GRID_N - 1):
            if grid[z][x] == 1:
                horiz = grid[z][x - 1] == 0 and grid[z][x + 1] == 0
                vert = grid[z - 1][x] == 0 and grid[z + 1][x] == 0
                if (horiz ^ vert) and random.random() < BRAID_RATIO:
                    grid[z][x] = 0
                    opened += 1
    print(f'（迷宫已生成：40x40 地块 | 随机打通 {opened} 面墙形成环路）')
    return grid


# =====================================================================================
#  六、实体类（全部继承 Entity；update() 第一行均为状态闸门）
# =====================================================================================
class Revealable(Entity):
    """可被回声"照亮"的实体基类：平时黑色实心；被声波扫中时切换为
    ★ 高亮青白色线框轮廓（规格：wireframe=True + rgba(0,255,255,200)），
    持续 1.5 秒后 invoke 延迟恢复。高亮期间清除 shader（无光照渲染），
    保证青白轮廓明亮通透不被灯光压暗。"""

    REVEAL_COLOR = color.rgba(0, 255, 255, 200)      # ★ 高亮青白色（规格值）

    def __init__(self, base_color=color.rgb(0, 0, 0), **kwargs):
        super().__init__(color=base_color, **kwargs)
        self.is_dead = False
        self.base_color = base_color

    def reveal(self):
        """被回声扫中：高亮青白色线框显形（持续 1.5 秒）"""
        if getattr(self, 'is_dead', False):
            return
        self.color = self.REVEAL_COLOR
        clear_shader(self)                     # 高亮期不受灯光影响
        set_wireframe(self, True)
        invoke(_delayed_restore, self, delay=REVEAL_RESTORE_DELAY)


def _delayed_restore(entity):
    """invoke 延迟恢复回调：先检查实体是否已销毁（防闪退），再恢复黑色实心"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    entity.color = entity.base_color
    apply_lit_shader(entity)                   # 恢复感光材质（微光视野）
    set_wireframe(entity, False)


class Wall(Revealable):
    """黑色迷宫墙，三种显示状态（mode 字段统一管理，避免被动线框与回声高亮打架）：
      'dark' —— 近黑实心（贴脸时被玩家点光照出微弱轮廓，默认态）
      'near' —— 玩家 4 米内：暗灰线框 rgba(50,50,50,α)（α 平滑渐变，绝不闪烁）
      'echo' —— 被回声扫中：高亮青白线框 1.5 秒，之后按当前距离恢复 near/dark
    ★ 平滑机制：near_alpha 每帧向目标指数逼近 + 进入/退出双阈值滞回带
      （4.0 米渐显 / 4.8 米才渐隐），玩家在边界来回走动也不会闪烁。"""

    BASE = color.rgb(18, 18, 20)               # 近黑：纯黑会完全吸光，轮廓不可见
    NEAR_R, NEAR_G, NEAR_B, NEAR_A = 50, 50, 50, 100   # 暗灰线框基色（规格值）
    MODE_DARK, MODE_NEAR, MODE_ECHO = 'dark', 'near', 'echo'

    def __init__(self, cx, cz):
        super().__init__(
            base_color=self.BASE,
            model='cube',
            position=(cx, WALL_HEIGHT / 2, cz),
            scale=(4, 4, 4),
        )
        self.mode = Wall.MODE_DARK
        self.near_alpha = 0.0                  # 近距线框透明度（平滑渐变用）
        apply_lit_shader(self)
        add_box_collider(self, size=Vec3(4, 4, 4))   # ★ 规格要求：完整墙体碰撞体

    def enter_near(self):
        """进入近距感知态：开启线框（只切换一次渲染模式，之后仅渐变透明度）"""
        self.mode = Wall.MODE_NEAR
        self.near_alpha = max(self.near_alpha, 0.05)
        self.color = color.rgba(Wall.NEAR_R, Wall.NEAR_G, Wall.NEAR_B, 5)
        clear_shader(self)
        set_wireframe(self, True)

    def set_dark(self):
        """恢复近黑实心（回声高亮期间不打断）"""
        if self.is_dead or self.mode == Wall.MODE_ECHO:
            return
        self.mode = Wall.MODE_DARK
        self.near_alpha = 0.0
        self.color = self.BASE
        apply_lit_shader(self)
        set_wireframe(self, False)

    def apply_near_alpha(self, alpha):
        """按平滑值刷新近距线框透明度（0~100）"""
        self.near_alpha = alpha
        a = max(4, int(Wall.NEAR_A * alpha))
        self.color = color.rgba(Wall.NEAR_R, Wall.NEAR_G, Wall.NEAR_B, a)

    def reveal(self):
        """回声扫中：高亮青白线框（优先级最高），1.5 秒后按距离恢复"""
        if getattr(self, 'is_dead', False):
            return
        self.mode = Wall.MODE_ECHO
        self.color = self.REVEAL_COLOR
        clear_shader(self)
        set_wireframe(self, True)
        invoke(_wall_restore, self, delay=REVEAL_RESTORE_DELAY)


def _wall_restore(wall):
    """墙体回声高亮结束：按玩家当前距离恢复为 near（4 米内）或 dark"""
    if wall is None or getattr(wall, 'is_dead', False):
        return
    if wall.mode != Wall.MODE_ECHO:
        return                                  # 已被其它状态接管
    if player is not None and dist_xz(wall.position, player.position) <= WALL_SENSE_ENTER:
        wall.enter_near()                       # 玩家仍贴着墙：转暗灰线框
        wall.apply_near_alpha(1.0)
    else:
        wall.set_dark()


class EchoSphere(Entity):
    """回声波：青白色线框球体，1.5 秒内从 0 膨胀到 scale=60（半径 30）。
    扫过的墙/怪物切换为高亮青白线框轮廓（见 Revealable/Wall）。"""

    def __init__(self, origin):
        super().__init__(
            model='sphere',
            wireframe=True,                       # 规格关键字：线框模式
            color=color.rgba(0, 255, 255, 110),   # 青白色声波
            position=origin,
            scale=0.01,
            double_sided=True,
        )
        self.is_dead = False
        self.wave_origin = Vec3(origin.x, origin.y, origin.z)
        self.elapsed = 0.0
        self.revealed = set()
        try:
            self.set_render_mode_filled_wireframe(2)   # 线框渲染双保险
        except Exception:
            try:
                self.set_render_mode_wireframe(2)
            except Exception:
                pass

    def _wave_reaches(self, wall, radius):
        """声波前沿是否已抵达该墙：XZ 平面上波源到墙块最近点的距离 ≤ 当前半径"""
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        nearest_x = clamp(self.wave_origin.x, wall.x - hx, wall.x + hx)
        nearest_z = clamp(self.wave_origin.z, wall.z - hz, wall.z + hz)
        dx = self.wave_origin.x - nearest_x
        dz = self.wave_origin.z - nearest_z
        return (dx * dx + dz * dz) <= radius * radius

    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead:
            return
        self.elapsed += time.dt
        ratio = min(self.elapsed / ECHO_DURATION, 1.0)
        self.scale = ECHO_MAX_SCALE * ratio
        radius = self.scale / 2.0

        # 扫描墙：切换为高亮青白线框（1.5 秒）
        for wall in list(WALLS):
            if wall.is_dead or wall in self.revealed:
                continue
            if self._wave_reaches(wall, radius):
                wall.reveal()
                self.revealed.add(wall)

        # 扫描怪物：身体同样切换为高亮青白线框轮廓（眼睛保持红色）
        for m in list(MONSTERS):
            if m.is_dead or m in self.revealed:
                continue
            if dist_xz(self.wave_origin, m.position) <= radius:
                m.reveal()
                self.revealed.add(m)

        if self.elapsed >= ECHO_DURATION:
            self.is_dead = True                    # 交由全局 update 清道夫销毁


class GroundRipple(Entity):
    """★ 地面声呐波纹（参考第五人格盲女）：贴地的发光青色线框圆环，
    以敲击点为中心迅速扩大并淡出——模拟声呐在水面/地面扩散的涟漪。
    每次敲击生成两道错峰圆环，营造涟漪层次感。"""

    DURATION = 1.1              # 波纹生命周期（秒）
    MAX_SCALE = 56.0            # 最大直径（半径约 28 米）

    def __init__(self, origin):
        super().__init__(
            model='circle',
            color=color.rgba(0, 255, 255, 210),
            position=Vec3(origin.x, 0.07, origin.z),   # 略高于地面避免 Z 闪烁
            rotation_x=90,                              # 平铺在地面
            scale=0.5,
            double_sided=True,
        )
        self.is_dead = False
        self.elapsed = 0.0
        try:
            self.set_render_mode_wireframe(2)          # 线框圆环
        except Exception:
            pass                                       # 退化为半透明圆盘，不影响效果

    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING or self.is_dead:
            return
        self.elapsed += time.dt
        r = min(self.elapsed / self.DURATION, 1.0)
        # 先快后慢的扩张（缓出曲线）——"迅速扩大"
        self.scale = 2.0 + (self.MAX_SCALE - 2.0) * (1.0 - (1.0 - r) ** 2)
        # 同步淡出
        self.color = color.rgba(0, 255, 255, max(0, int(210 * (1.0 - r))))
        if self.elapsed >= self.DURATION:
            self.is_dead = True                       # 交由全局 update 清道夫销毁


def spawn_delayed_ripple(origin):
    """敲击后 0.3 秒生成第二道涟漪（invoke 延迟回调，需检查状态防闪退）"""
    if game_state == GameState.PLAYING:
        RIPPLES.append(GroundRipple(origin))


class Stone(Entity):
    """投掷石（F）：向前发射的小球，飞行 1.5 秒后落地（撞墙提前），
    落地点向所有怪物广播"假噪音"——声东击西。CD 3 秒。"""

    def __init__(self, position, direction):
        super().__init__(
            model='sphere',
            color=color.rgb(20, 20, 22),
            position=position,
            scale=0.32,
        )
        self.is_dead = False
        h = Vec3(direction.x, 0, direction.z)
        if h.length() < 0.01:
            h = Vec3(player.forward.x, 0, player.forward.z) if player else Vec3(0, 0, -1)
        self.velocity = h.normalized() * STONE_SPEED
        self.flight_t = 0.0
        apply_lit_shader(self)                  # 石头近脸时借点光隐约可见
        add_box_collider(self, size=Vec3(0.3, 0.3, 0.3))

    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead:
            return
        dt = time.dt
        self.flight_t += dt
        self.position += self.velocity * dt
        self.y -= STONE_GRAVITY * self.flight_t * dt   # 轻微下坠弧线
        hit_wall = False
        for wall in list(WALLS):
            if wall.is_dead:
                continue
            if abs(wall.x - self.x) > TILE or abs(wall.z - self.z) > TILE:
                continue
            hx = wall.scale[0] / 2.0
            hz = wall.scale[2] / 2.0
            nearest_x = clamp(self.x, wall.x - hx, wall.x + hx)
            nearest_z = clamp(self.z, wall.z - hz, wall.z + hz)
            dx = self.x - nearest_x
            dz = self.z - nearest_z
            if dx * dx + dz * dz <= 0.09 and self.y < wall.scale[1]:
                hit_wall = True
                break
        if self.flight_t >= STONE_LIFE or self.y <= 0.15 or hit_wall:
            self.y = max(self.y, 0.15)
            self.is_dead = True
            play_sfx('monster_step', volume=0.5)        # 落地闷响
            emit_noise(self.position, ALL_MONSTERS)     # ★ 假噪音广播


class Fuse(Entity):
    """发光保险丝：微弱黄光的圆柱体，靠近按 E 收集；集齐 3 枚激活出口。
    ★ 被动指引：玩家 10 米内脉动式闪烁（更快更亮的呼吸 + 尺寸脉动），
    并由全局 update 触发微弱的电流"滋滋"声。"""

    def __init__(self, position):
        super().__init__(
            model='cylinder',
            position=position + Vec3(0, 0.7, 0),
            scale=0.5,
            color=color.rgb(255, 200, 70),
        )
        self.is_dead = False
        self.near = False                       # 玩家是否在 10 米内（全局 update 刷新）
        self.pulse_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.6, 1.5, 0.6))

    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead:
            return
        self.pulse_t += time.dt
        if self.near:
            # 近距：更快的脉动 + 尺寸呼吸（救赎的指引，规格要求）
            b = 0.5 + 0.5 * math.sin(self.pulse_t * 4.0)
            self.scale = 0.5 + 0.08 * math.sin(self.pulse_t * 4.0)
            self.rotation_y += 90 * time.dt
        else:
            # 远距：缓慢微弱的呼吸
            b = 0.35 + 0.35 * abs(math.sin(self.pulse_t * 1.8))
            self.scale = 0.5
            self.rotation_y += 45 * time.dt
        self.color = color.rgb(255, int(140 + 100 * b), int(30 + 60 * b))
        self.y = 0.7 + 0.1 * math.sin(self.pulse_t * 1.2)


class ExitGate(Entity):
    """迷宫出口：绿灯在集齐 3 枚保险丝前熄灭，集齐后亮起脉动；触碰 → WIN。"""

    def __init__(self, position):
        super().__init__(
            model='cube',
            position=position + Vec3(0, 1.5, 0),
            scale=(1.2, 3.0, 1.2),
            color=color.rgb(15, 40, 22),
        )
        self.is_dead = False
        self.locked = True
        self.pulse_t = 0.0
        self.hint_cd = 0.0
        add_box_collider(self, size=Vec3(1.2, 3.0, 1.2))

    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead:
            return
        self.pulse_t += time.dt
        self.hint_cd = max(0.0, self.hint_cd - time.dt)
        if self.locked:
            self.color = color.rgb(15, 40, 22)
        else:
            b = 0.65 + 0.35 * math.sin(self.pulse_t * 3.0)
            self.color = color.rgb(int(30 + 90 * b), int(150 + 105 * b), int(70 + 70 * b))

    def unlock(self):
        self.locked = False


class Monster(Entity):
    """盲眼怪物：优先加载 monster.obj（同目录规格资源/网络下载，自动归一化到
    3.2 米高），失败则用组合人形拼凑——黑色细长身体 + 头颅 + 双臂（下垂微张）
    + 两颗滴血般发红光的球体眼睛——"像怪物而不是一个方块"。
    状态机：PATROL 巡逻(沉重喘息) → CHASE 冲刺(切态瞬间嘶吼震慑)
            → SEARCH 原地转圈 3 秒。距离 < 1.2 → 触发突脸 + 扣命。"""

    RADIUS = 0.6
    BODY_BASE_COLOR = color.rgb(10, 10, 12)

    def __init__(self, spawn_tile):
        world = level_manager.tile_to_world(spawn_tile)
        super().__init__(position=(world.x, 0, world.z))   # 根节点：无模型，负责逻辑
        self.is_dead = False
        self.spawn_tile = spawn_tile            # 出生地块（巡逻中心/搜完返回点）
        self.state = 'PATROL'
        self.path = []
        self.noise_target = None
        self.wander_timer = 0.0
        self.search_timer = 0.0
        self.cry_timer = 0.0
        self.breath_timer = random.uniform(0.5, 2.0)
        self.parts = []                         # 身体部件列表（回声高亮/恢复统一处理）
        self._build_body()
        # 两颗滴血般的红色发光眼睛（漂浮在头颅前，无光照渲染保持鲜红）
        self.eye_l = Entity(parent=self, model='sphere',
                            scale=0.09, position=(-0.11, 2.72, -0.26),
                            color=color.rgb(255, 30, 30))
        self.eye_r = Entity(parent=self, model='sphere',
                            scale=0.09, position=(0.11, 2.72, -0.26),
                            color=color.rgb(255, 30, 30))
        # ★ 规格要求：怪物碰撞体（显式尺寸，根节点无模型也安全）
        add_box_collider(self, center=Vec3(0, 1.6, 0), size=Vec3(1.0, 3.2, 1.0))

    def _build_body(self):
        """构建身体：monster.obj（归一化高度）→ 失败回退组合人形（身体+头+双臂）。"""
        self.body = None
        if MONSTER_OBJ_PATH:
            try:
                body = Entity(parent=self, model=MONSTER_OBJ_PATH,
                              color=self.BODY_BASE_COLOR)
                # 用紧致包围盒把模型归一化到 3.2 米高，防止外部模型比例失控
                mn, mx = body.get_tight_bounds()
                size = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z, 0.001)
                body.scale = 3.2 / size
                body.y = 1.6 / body.scale_y      # 让身体底部贴地（中心抬到半高）
                self.body = body
                self.parts = [body]
                apply_lit_shader(body)
                return
            except Exception:
                if self.body is not None:
                    try:
                        destroy(self.body)
                    except Exception:
                        pass
                self.body = None
        # 回退：组合人形——细长身体 + 头颅 + 双臂（下垂微张，佝偻瘦长的剪影）
        self.body = Entity(parent=self, model='cube',
                           scale=(0.7, 2.6, 0.45), y=1.3,
                           color=self.BODY_BASE_COLOR)
        head = Entity(parent=self, model='cube',
                      scale=(0.42, 0.4, 0.4), position=(0, 2.72, -0.03),
                      color=self.BODY_BASE_COLOR)
        arm_l = Entity(parent=self, model='cube',
                       scale=(0.13, 1.5, 0.13), position=(-0.48, 1.55, 0.0),
                       rotation_z=0.10, color=self.BODY_BASE_COLOR)
        arm_r = Entity(parent=self, model='cube',
                       scale=(0.13, 1.5, 0.13), position=(0.48, 1.55, 0.0),
                       rotation_z=-0.10, color=self.BODY_BASE_COLOR)
        self.parts = [self.body, head, arm_l, arm_r]
        for p in self.parts:
            apply_lit_shader(p)                 # 部件感光：贴近时借玩家点光现出剪影

    # ---------------- 回声高亮：全部身体部件高亮青白线框 1.5 秒 ----------------
    def reveal(self):
        if self.is_dead:
            return
        for p in self.parts:
            p.color = Revealable.REVEAL_COLOR
            clear_shader(p)
            set_wireframe(p, True)
        invoke(_delayed_monster_restore, self, delay=REVEAL_RESTORE_DELAY)

    # ---------------- 状态复位（生成/扣命重生时共用） ----------------
    def reset(self):
        """回到出生地块，恢复巡逻状态与原始模型外观"""
        w = level_manager.tile_to_world(self.spawn_tile)
        self.position = Vec3(w.x, 0, w.z)
        self.state = 'PATROL'
        self.path = []
        self.wander_timer = 0.0
        self.search_timer = 0.0
        for p in self.parts:
            p.color = self.BODY_BASE_COLOR
            apply_lit_shader(p)
            set_wireframe(p, False)
        # 突脸时眼睛被放大下移——这里恢复原始大小位置
        for eye in (self.eye_l, self.eye_r):
            eye.y = 2.72
            eye.scale = 0.09
            eye.color = color.rgb(255, 30, 30)

    # ---------------- 死亡突脸（Jumpscare）----------------
    def play_jumpscare(self):
        """突脸：瞬移到相机正前方 0.5 米、面向玩家、红色巨眼逼近视线高度。
        相机剧烈抖动/尖叫/扣命由 update 与 lose_life 驱动。"""
        cam = camera.world_position
        fwd = camera.forward
        tx = cam.x + fwd.x * SCARE_DIST           # 相机正前方 0.5 米（规格值）
        tz = cam.z + fwd.z * SCARE_DIST
        self.position = Vec3(tx, 0, tz)
        self.rotation_y = math.degrees(math.atan2(cam.x - tx, -(cam.z - tz)))
        self.state = 'SCARE'
        for eye in (self.eye_l, self.eye_r):      # 眼睛下移到视线高度并骤然放大
            eye.y = 1.9
            eye.scale = 0.45
            eye.color = color.rgb(255, 20, 20)
        for p in self.parts:
            p.color = color.rgb(20, 0, 0)

    # ---------------- 感知：噪音事件入口 ----------------
    def hear_noise(self, position, radius):
        """听到噪音（回声敲击/奔跑/石头落地）：可听半径内切换 CHASE。
        ★ PATROL→CHASE 的切态瞬间播放 monster_scream（嘶吼），震慑玩家。"""
        if self.is_dead or game_state != GameState.PLAYING or scare_active:
            return
        if radius < ALL_MONSTERS and dist_xz(self.position, position) > radius:
            return                                 # 超出可听半径：听不见
        lm = level_manager
        goal = lm.nearest_floor_tile(position)
        self.noise_target = lm.tile_to_world(goal)
        cells = lm.bfs_path(lm.world_to_tile(self.position), goal)
        self.path = [lm.tile_to_world(t) for t in cells] if cells else [self.noise_target]
        if self.state != 'CHASE':
            self.state = 'CHASE'
            self.cry_timer = 1.5
            play_sfx('roar', volume=0.9)           # ★ 追击嘶吼（monster_scream）
            print('【怪物嘶吼】呃 啊 啊 啊——！！它扑向了声源！')

    # ---------------- 行为辅助 ----------------
    def _follow_path(self, speed):
        if not self.path:
            return True
        target = self.path[0]
        dx = target.x - self.x
        dz = target.z - self.z
        d = math.hypot(dx, dz)
        if d < 0.35:
            self.path.pop(0)
            return len(self.path) == 0
        step = min(speed * time.dt, d)
        self.x += dx / d * step
        self.z += dz / d * step
        self.rotation_y = math.degrees(math.atan2(dx, -dz))
        resolve_collisions(self, self.RADIUS)
        push_out_if_stuck(self)                 # ★ 卡墙保护：怪物也不会卡进墙里
        return False

    def _pick_patrol_destination(self):
        """PATROL：在怪物出生点周围随机选一个房间游荡（BFS 2~5 步可达）"""
        lm = level_manager
        cur = lm.world_to_tile(self.position)
        spawn_dists = lm.bfs_distances(self.spawn_tile)
        cands = [t for t, d in spawn_dists.items() if 2 <= d <= 5]
        goal = random.choice(cands) if cands else lm.random_floor_tile()
        cells = lm.bfs_path(cur, goal)
        self.path = ([lm.tile_to_world(t) for t in cells]
                     if cells else [lm.tile_to_world(goal)])
        self.wander_timer = random.uniform(5.0, 9.0)

    def _breath(self):
        """PATROL 期间发出沉重的喘息声（音频 + 近距文字提示）"""
        if player is None:
            return
        d = dist_xz(self.position, player.position)
        if d > 18:
            return
        vol = 0.15 + 0.5 * clamp(1 - d / 18.0, 0, 1)   # 越近喘息越响
        play_sfx('mbreath', volume=vol, pitch=random.uniform(0.85, 1.05))
        if d < 10:
            print(f'【怪物喘息】呼——嘶——（约{d:.0f}米）')

    # ---------------- 每帧逻辑（Ursina 引擎自动调用） ----------------
    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead or player is None or scare_active:
            return                                  # 突脸期间全体怪物冻结
        dt = time.dt

        if self.state == 'PATROL':
            self.breath_timer -= dt
            if self.breath_timer <= 0:
                self.breath_timer = 2.2
                self._breath()
            arrived = self._follow_path(MONSTER_PATROL_SPEED)
            self.wander_timer -= dt
            if arrived or self.wander_timer <= 0:
                self._pick_patrol_destination()

        elif self.state == 'CHASE':
            self.cry_timer -= dt
            if self.cry_timer <= 0:
                self.cry_timer = 1.5
                d = dist_xz(self.position, player.position)
                print(f'【怪物】沉重的疾行声……（距离约 {d:.1f} 米）')
            arrived = self._follow_path(MONSTER_CHASE_SPEED)
            if arrived:
                self.state = 'SEARCH'
                self.search_timer = 3.0
                print('【怪物】嘶……嘶……（它到达声源，原地搜寻）')

        elif self.state == 'SEARCH':
            self.rotation_y += 120 * dt            # 原地旋转 360 度搜索 3 秒
            self.search_timer -= dt
            if self.search_timer <= 0:
                self.state = 'PATROL'
                lm = level_manager
                cells = lm.bfs_path(lm.world_to_tile(self.position), self.spawn_tile)
                self.path = ([lm.tile_to_world(t) for t in cells]
                             if cells else [lm.tile_to_world(self.spawn_tile)])
                self.wander_timer = 5.0
                print('【怪物】一无所获……它退回黑暗深处')

        # ---- 致杀判定：距离 < 1.2 → 触发突脸（相机抖动后扣命）----
        if not getattr(player, 'is_dead', False):
            if dist_xz(self.position, player.position) < KILL_DISTANCE:
                start_jumpscare(self)


def _delayed_monster_restore(monster):
    """invoke 延迟恢复怪物身体部件的黑色实心（检查 is_dead 防闪退）"""
    if monster is None or getattr(monster, 'is_dead', False):
        return
    for p in monster.parts:
        p.color = Monster.BODY_BASE_COLOR
        apply_lit_shader(p)
        set_wireframe(p, False)


class Player(Entity):
    """第一人称玩家：无任何战斗手段，3 条命，随身携带微弱点光源。
    WASD 移动 | Shift 奔跑(×1.8·耗体·巨响) | 左键按住潜行(半速·无声·回体)
    右键回声定位（线框球+地面波纹+小地图）| F 扔石头 | E 收集保险丝。
    恐惧发抖：怪物逼近时（danger_k）视点出现轻微高频晃动，与晕影同步。"""

    PLAYER_RADIUS = 0.5
    MOUSE_SENSITIVITY = 40.0

    def __init__(self, position, yaw=0):
        super().__init__(position=position, rotation_y=yaw)
        self.is_dead = False
        self.stamina = BASE_MAX_STAMINA
        self.echo_cooldown = 0.0
        self.stone_cooldown = 0.0
        self.step_accum = 0.0
        self.skill_radar = False                 # 雷达强化：回声半径 ×1.5（本局）
        self.skill_silent = False                # 静步大师：移动 0 噪音（本局）
        self.spawn_position = Vec3(position.x, 0, position.z)   # 出生点（扣命重生用）
        self._base_h = STAND_HEIGHT              # 视点基础高度（发抖偏移单独叠加）
        self.camera_pivot = Entity(parent=self, y=STAND_HEIGHT)
        camera.parent = self.camera_pivot
        camera.position = Vec3(0, 0, 0)
        camera.rotation = Vec3(0, 0, 0)
        camera.fov = 90
        # ★ 规格要求：玩家碰撞体（显式尺寸，配合墙体碰撞与卡墙保护防穿模）
        add_box_collider(self, center=Vec3(0, 1.0, 0), size=Vec3(0.9, 1.9, 0.9))
        # ★ 微光视野：摄像机随身点光源——勉强照亮脚下与周围 3~4 米内的物体轮廓，
        # 稍远处被黑雾吞噬。挂在 camera_pivot 上：视角转到哪里微光就跟到哪里，
        # 且随玩家一起销毁（防止重开后灯光累积）。
        self.player_light = None
        try:
            self.player_light = PointLight(parent=self.camera_pivot,
                                           color=color.rgba(80, 80, 80, 50),
                                           distance=4, shadows=False)
        except Exception:
            self.player_light = None             # 光照接口不可用：静默降级

    # ---------------- 主动作 ----------------
    def try_echo(self):
        """鼠标右键敲击地面（回声定位）：CD 4 秒，耗 10 体力。
        ① 膨胀线框球照亮世界 ② ★ 地面青色声呐波纹（双环错峰扩散）
        ③ 左上角小地图短暂显示——敲击声极大，惊动所有怪物！"""
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        if self.echo_cooldown > 0:
            return
        if self.stamina < ECHO_STAMINA_COST:
            print('【回声】体力不足，无法凝聚听觉（需要 10 点体力）')
            return
        self.stamina -= ECHO_STAMINA_COST
        self.echo_cooldown = ECHO_COOLDOWN
        origin = Vec3(self.position.x, self.position.y, self.position.z)
        ECHO_SPHERES.append(EchoSphere(origin + Vec3(0, 1.0, 0)))
        RIPPLES.append(GroundRipple(origin))                  # ★ 地面波纹（第一道）
        invoke(spawn_delayed_ripple, Vec3(origin.x, origin.y, origin.z),
               delay=0.3)                                     # ★ 第二道错峰涟漪
        play_sfx('sonar')
        refresh_minimap()                        # ★ 敲击时显示小地图（1.5 秒后隐藏）
        emit_noise(self.position, ALL_MONSTERS)  # ★ 敲击 = 极大噪音

    def throw_stone(self):
        """投掷石头（F）：CD 3 秒，飞行 1.5 秒后落地广播假噪音。"""
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        if self.stone_cooldown > 0:
            return
        self.stone_cooldown = STONE_COOLDOWN
        d = camera.forward
        STONES.append(Stone(camera.world_position + Vec3(0, 0.1, 0), d))
        print('（嗖——石头脱手飞出）')

    def try_pickup(self):
        """交互（E）：收集近处保险丝；集齐 3 枚 → 出口绿灯亮起。"""
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        global collected_fuses
        nearest, nearest_d = None, 1.8
        for f in list(FUSES):
            if f.is_dead:
                continue
            d = dist_xz(self.position, f.position)
            if d < nearest_d:
                nearest, nearest_d = f, d
        if nearest is None:
            return
        safe_destroy(nearest)
        collected_fuses += 1                     # ★ 扣命重生时保留该计数
        update_status_text()
        print('【保险丝】咔哒——你拔下一枚微光保险丝')
        if collected_fuses >= FUSES_NEEDED and level_manager.exit_gate is not None:
            level_manager.exit_gate.unlock()
            print('【出口】三枚保险丝嵌入凹槽——出口绿灯亮起！')

    def activate_skill(self, key):
        """Tab 面板激活技能：耗 30 体力，每局各一次（体力不足则失败提示）"""
        if game_state != GameState.SKILL_SELECT or self.is_dead:
            return False
        already = (key == 'radar' and self.skill_radar) or \
                  (key == 'silent' and self.skill_silent)
        if already:
            show_toast('该技能已激活')
            return False
        if self.stamina < SKILL_COST:
            show_toast('体力不足（需要 30 点）')
            return False
        self.stamina -= SKILL_COST
        if key == 'radar':
            self.skill_radar = True
        elif key == 'silent':
            self.skill_silent = True
        play_sfx('skill')
        show_toast(f'技能激活：{SKILLS[key]["name"]}')
        return True

    def respawn(self):
        """扣命重生：瞬移回出生点、回满体力、复位视点（保险丝计数保留）"""
        self.position = Vec3(self.spawn_position.x, 0, self.spawn_position.z)
        self.stamina = BASE_MAX_STAMINA
        self.echo_cooldown = 0.0
        self.stone_cooldown = 0.0
        self._base_h = STAND_HEIGHT              # 复位视点基础高度（发抖偏移归零）
        self.camera_pivot.x = 0.0                # 复位突脸抖动偏移
        self.camera_pivot.y = STAND_HEIGHT
        self.camera_pivot.rotation_x = 0.0

    # ---------------- 每帧逻辑（Ursina 引擎自动调用） ----------------
    def update(self):
        # ★ 防闪退铁律第一行
        if game_state != GameState.PLAYING:
            return
        if self.is_dead or scare_active:
            return                                # 突脸期间冻结输入（抖动在全局 update）
        dt = time.dt

        # ---- 冷却推进 ----
        self.echo_cooldown = max(0.0, self.echo_cooldown - dt)
        self.stone_cooldown = max(0.0, self.stone_cooldown - dt)

        # ---- 视角：鼠标控制，X 轴（俯仰）限制 -80 ~ 80 度 ----
        self.rotation_y += mouse.velocity[0] * self.MOUSE_SENSITIVITY
        self.camera_pivot.rotation_x = clamp(
            self.camera_pivot.rotation_x - mouse.velocity[1] * self.MOUSE_SENSITIVITY,
            -80, 80)

        # ---- 输入意图：左键按住 = 潜行；Shift = 奔跑 ----
        sneaking = held_keys['left mouse'] == 1
        want_run = (held_keys['left shift'] or held_keys['right shift']) and not sneaking
        ix = held_keys['d'] - held_keys['a']
        iz = held_keys['s'] - held_keys['w']
        moving = ix != 0 or iz != 0

        # ---- 体力：奔跑每帧耗 0.5（×60×dt 帧率无关化）；潜行回体最快 ----
        running = False
        if want_run and moving and self.stamina > 0:
            running = True
            self.stamina -= RUN_DRAIN_PER_FRAME * 60.0 * dt
            if self.stamina <= 0:
                self.stamina = 0.0
                print('【体力】跑不动了……')
        if not running:
            regen = REGEN_SNEAK if sneaking else REGEN_NORMAL
            self.stamina = min(BASE_MAX_STAMINA, self.stamina + regen * dt)

        # ---- 移动三态：潜行(0.5×) < 基础(1.0×) < 奔跑(1.8×) ----
        if sneaking:
            speed, mode = WALK_SPEED * SNEAK_MULT, 'sneak'
        elif running:
            speed, mode = WALK_SPEED * RUN_MULT, 'run'
        else:
            speed, mode = WALK_SPEED, 'walk'

        # ---- 实际移动 + 噪音管理 ----
        if moving:
            direction = (self.forward * (-iz) + self.right * ix).normalized()
            self.position += direction * speed * dt
            resolve_collisions(self, self.PLAYER_RADIUS)   # 墙体碰撞（防穿墙）
            push_out_if_stuck(self)                        # ★ 卡墙强推保护
            if mode != 'sneak' and not self.skill_silent:
                self.step_accum += speed * dt
                step_len = 2.2 if mode == 'walk' else 2.6
                if self.step_accum >= step_len:
                    self.step_accum = 0.0
                    if mode == 'run':
                        emit_noise(self.position, RUN_NOISE)
                        play_sfx('step_run', volume=0.9,
                                 pitch=random.uniform(0.9, 1.1))
                    else:
                        emit_noise(self.position, WALK_NOISE)
                        play_sfx('step', volume=0.6,          # 随机音调的脚步声
                                 pitch=random.uniform(0.85, 1.15))

        # ---- 视点：基础高度平滑 + 恐惧发抖偏移（怪物逼近时轻微晃动）----
        self._base_h = lerp(self._base_h, STAND_HEIGHT, min(dt * 8, 1))
        self.camera_pivot.y = self._base_h \
            + math.sin(pytime.time() * 9.3) * 0.007 * danger_k
        self.camera_pivot.x = math.sin(pytime.time() * 11.0) * 0.009 * danger_k

        # ---- 体力条 UI 同步：底部绿色四边形随体力动态缩放 ----
        frac = self.stamina / BASE_MAX_STAMINA
        stamina_fill.scale = Vec3(0.62 * frac, 0.035, 1)
        stamina_fill.color = (color.rgb(70, 150, 60) if self.stamina <= 0
                              else color.rgb(60, 220, 90))


# =====================================================================================
#  七、关卡管理器（LevelManager）—— 40x40 DFS 大迷宫的生成 / 寻路 / 销毁
# =====================================================================================
class LevelManager:
    """关卡管理器：DFS 生成 40x40 大迷宫（含随机打墙环路），遍历数组搭建 3D 世界，
    放置玩家(0,0角)/3 保险丝(死胡同)/出口/怪物；内含地块换算与 BFS 精确寻路。"""

    def __init__(self):
        self.grid = []
        self.floor_tiles = []
        self.dead_ends = []
        self.spawn_tile = (1, 1)
        self.ground = None
        self.exit_gate = None
        self.player = None

    # ---------------- 地块 ↔ 世界坐标换算 ----------------
    def tile_to_world(self, tile):
        x, z = tile
        return Vec3((x - (GRID_N - 1) / 2) * TILE, 0,
                    (z - (GRID_N - 1) / 2) * TILE)

    def world_to_tile(self, pos):
        return (round(pos.x / TILE + (GRID_N - 1) / 2),
                round(pos.z / TILE + (GRID_N - 1) / 2))

    def is_floor(self, tile):
        x, z = tile
        return 0 <= x < GRID_N and 0 <= z < GRID_N and self.grid[z][x] == 0

    def _neighbors(self, tile):
        x, z = tile
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, z + dz)
            if self.is_floor(nb):
                yield nb

    # ---------------- BFS：精确寻路与距离表 ----------------
    def bfs_path(self, start, goal):
        if not self.is_floor(start) or not self.is_floor(goal):
            return None
        if start == goal:
            return []
        prev = {start: None}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            if cur == goal:
                break
            for nb in self._neighbors(cur):
                if nb not in prev:
                    prev[nb] = cur
                    queue.append(nb)
        if goal not in prev:
            return None
        path = []
        c = goal
        while prev[c] is not None:
            path.append(c)
            c = prev[c]
        path.reverse()
        return path

    def bfs_distances(self, start):
        dists = {start: 0}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            for nb in self._neighbors(cur):
                if nb not in dists:
                    dists[nb] = dists[cur] + 1
                    queue.append(nb)
        return dists

    def nearest_floor_tile(self, pos):
        tile = self.world_to_tile(pos)
        if self.is_floor(tile):
            return tile
        best, best_d = None, 10 ** 9
        for t in self.floor_tiles:
            d = (t[0] - tile[0]) ** 2 + (t[1] - tile[1]) ** 2
            if d < best_d:
                best, best_d = t, d
        return best

    def random_floor_tile(self):
        return random.choice(self.floor_tiles)

    # ---------------- 关卡生成全流程 ----------------
    def load_level(self):
        """生成关卡：DFS 迷宫(含环路) → 地形 → 玩家(0,0角) → 保险丝/出口(死胡同) → 怪物"""
        global player
        self.teardown()
        # ---- 1. DFS 迷宫（40x40 + 随机打墙）与死胡同统计 ----
        self.grid = generate_maze_grid()
        self.floor_tiles = [(x, z) for z in range(GRID_N) for x in range(GRID_N)
                            if self.grid[z][x] == 0]
        self.dead_ends = []
        for (x, z) in self.floor_tiles:
            if x % 2 == 1 and z % 2 == 1:
                if sum(1 for _ in self._neighbors((x, z))) == 1:
                    self.dead_ends.append((x, z))

        # ---- 2. 地形：极暗地面（感光）+ 逐地块近黑墙块（感光+碰撞体）----
        map_span = GRID_N * TILE                   # 160x160 米
        self.ground = Entity(model='plane', scale=(map_span, map_span),
                             color=color.rgb(12, 12, 14))
        self.ground.is_dead = False
        apply_lit_shader(self.ground)
        for z in range(GRID_N):
            for x in range(GRID_N):
                if self.grid[z][x] == 1:
                    w = self.tile_to_world((x, z))
                    WALLS.append(Wall(w.x, w.z))

        # ---- 3. 玩家出生在网格 (0,0) 角的第一个房间 (1,1) ----
        self.spawn_tile = (1, 1)
        dists = self.bfs_distances(self.spawn_tile)

        # ---- 4. 出口：最远死胡同之一；保险丝：远处死胡同随机 3 个 ----
        far_dead = sorted(self.dead_ends, key=lambda t: -dists.get(t, 0))
        exit_tile = random.choice(far_dead[:3]) if far_dead else self.random_floor_tile()
        used = {exit_tile, self.spawn_tile}
        self.exit_gate = ExitGate(self.tile_to_world(exit_tile))

        fuse_pool = [t for t in self.dead_ends
                     if dists.get(t, 0) >= 8 and t not in used]
        random.shuffle(fuse_pool)
        fuse_tiles = []
        for t in fuse_pool:
            if all(abs(t[0] - o[0]) + abs(t[1] - o[1]) >= 8 for o in fuse_tiles):
                fuse_tiles.append(t)
                used.add(t)
            if len(fuse_tiles) >= FUSES_NEEDED:
                break
        while len(fuse_tiles) < FUSES_NEEDED:      # 兜底：死胡同不足时放宽条件
            t = random.choice([t for t in self.floor_tiles if t not in used])
            fuse_tiles.append(t)
            used.add(t)
        for t in fuse_tiles:
            FUSES.append(Fuse(self.tile_to_world(t)))

        # ---- 5. 怪物：中远程位置盘踞（大地图 3 只），彼此保持距离 ----
        monster_pool = [t for t in self.floor_tiles
                        if dists.get(t, 0) >= 12 and t not in used]
        random.shuffle(monster_pool)
        monster_tiles = []
        for t in monster_pool:
            if all(abs(t[0] - o[0]) + abs(t[1] - o[1]) >= 8 for o in monster_tiles):
                monster_tiles.append(t)
                used.add(t)
            if len(monster_tiles) >= MONSTER_COUNT:
                break
        while len(monster_tiles) < MONSTER_COUNT:
            monster_tiles.append(self.random_floor_tile())
        for t in monster_tiles:
            MONSTERS.append(Monster(t))

        # ---- 6. 玩家：出生在角落房间，面朝第一个开放方向 ----
        yaw = 0
        for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if self.is_floor((self.spawn_tile[0] + dx, self.spawn_tile[1] + dz)):
                yaw = math.degrees(math.atan2(dx, -dz))
                break
        self.player = Player(self.tile_to_world(self.spawn_tile), yaw)
        player = self.player                    # ★ 同步全局引用

        print('=' * 56)
        print('  幽暗回廊（DFS 递归回溯 40x40 大迷宫，160x160 米）')
        print(f'  生命 ×{START_LIVES} | 死胡同 {len(self.dead_ends)} 个'
              f' | 收集 3 枚保险丝，出口绿灯亮起')
        print('  保持安静……它在听。')
        print('=' * 56)

    # ---------------- 场景清理：销毁一切实体，清空所有列表 ----------------
    def teardown(self):
        """★ 切换场景必调用：遍历所有实体安全销毁并清空列表（防幽灵碰撞）。
        玩家销毁时其 camera_pivot（含点光源）一并销毁——灯光不会跨局累积。"""
        global player, scare_active, scare_timer, monster_step_timer
        global buzz_timer, ambient_event_timer, danger_k
        camera.parent = scene
        camera.position = Vec3(0, 16, -30)
        camera.rotation = Vec3(35, 0, 0)
        for lst in (ECHO_SPHERES, RIPPLES, STONES, FUSES, MONSTERS, WALLS):
            for e in list(lst):                 # ★ 浅拷贝遍历再销毁
                e.is_dead = True
                destroy(e)
            lst.clear()
        for target in (self.exit_gate, self.ground, self.player):
            if target is not None:
                target.is_dead = True
                destroy(target)
        self.exit_gate = None
        self.ground = None
        self.player = None
        player = None
        scare_active = False
        scare_timer = 0.0
        monster_step_timer = 0.0
        buzz_timer = 0.0
        ambient_event_timer = random.uniform(6.0, 12.0)
        danger_k = 0.0


# =====================================================================================
#  八、小地图（左上角 UI）：敲击地面时显示 1.5 秒，中央箭头实时指向玩家朝向
# =====================================================================================
minimap_panel = None         # 暗色半透明背景板
minimap_cells = []           # 墙体格子对象池（青线，规格要求）
minimap_marks = {}           # 亮点标记对象池：fuse(黄)/monster(红)
minimap_arrow = None         # ★ 玩家指向箭头（三角形，旋转实时绑定玩家朝向）
_minimap_token = [0]         # 防止旧延迟任务误关新地图


def build_minimap():
    """构建小地图：背景板 + 墙体格子池（青线）+ 目标亮点池 + 中央指向箭头"""
    global minimap_panel, minimap_cells, minimap_marks, minimap_arrow
    minimap_panel = Entity(parent=camera.ui, model='quad',
                           color=color.rgba(12, 12, 16, 190),
                           scale=(MINIMAP_SIZE, MINIMAP_SIZE),
                           position=window.top_left + Vec2(0.22, -0.22),
                           z=-0.05)
    minimap_panel.enabled = False
    # 墙体格子池：青色小方块（每格对应 4 米地块；规格：墙壁画青线）
    cell = MINIMAP_SIZE * TILE / (MINIMAP_VIEW * 2)      # 地块在小地图上的尺寸
    minimap_cells = []
    for _ in range(MINIMAP_CELL_POOL):
        c = Entity(parent=minimap_panel, model='quad',
                   color=color.rgb(0, 200, 200), scale=(cell, cell, 1),
                   enabled=False)
        minimap_cells.append(c)
    # 目标亮点池：3 保险丝(黄) + 3 怪物(红)
    minimap_marks = {}
    for kind, count, col, size in (
            ('fuse', FUSES_NEEDED + 2, color.rgb(255, 210, 70), 0.030),
            ('monster', MONSTER_COUNT + 2, color.rgb(255, 60, 60), 0.036)):
        minimap_marks[kind] = [Entity(parent=minimap_panel, model='quad',
                                      color=col, scale=(size, size, 1), enabled=False)
                               for _ in range(count)]
    # ★ 玩家箭头：三角形模型（顶点朝上=北），亮青色；rotation_z 实时绑定玩家朝向
    try:
        arrow_mesh = Mesh(vertices=[Vec3(0, 1, 0),      # 顶点（朝上=前方）
                                    Vec3(-0.7, -0.6, 0),  # 左下
                                    Vec3(0.7, -0.6, 0)],  # 右下
                          mode='triangle')
        minimap_arrow = Entity(parent=minimap_panel, model=arrow_mesh,
                               color=color.rgb(120, 255, 230), scale=0.055)
    except Exception:
        # Mesh 三角形不可用时退化为菱形四边形箭头（仍能指示方向）
        minimap_arrow = Entity(parent=minimap_panel, model='quad',
                               color=color.rgb(120, 255, 230), scale=(0.028, 0.045))
    minimap_arrow.position = (0, 0)            # 地图正中央 = 玩家


def refresh_minimap():
    """敲击地面时刷新小地图：周围 20 米墙体画青色格子、附近保险丝/怪物画亮点，
    1.5 秒后自动隐藏。坐标映射：世界偏移 × (面板半宽 / 视野半径)，并夹取在边界内。"""
    _minimap_token[0] += 1
    token = _minimap_token[0]
    minimap_panel.enabled = True
    invoke(_hide_minimap, token, delay=1.5)
    if player is None:
        return
    half = MINIMAP_SIZE / 2.0
    sx = half / MINIMAP_VIEW                     # 世界米 → UI 比例

    # ---- 1. 墙体格子（玩家周围 20 米内，坐标夹取在面板边界内）----
    idx = 0
    for wall in list(WALLS):
        if wall.is_dead or idx >= len(minimap_cells):
            continue
        dx = wall.x - player.x
        dz = wall.z - player.z
        if abs(dx) > MINIMAP_VIEW or abs(dz) > MINIMAP_VIEW:
            continue                             # 只画"周围 20 米内的墙壁"
        c = minimap_cells[idx]
        idx += 1
        c.enabled = True
        c.x = clamp(dx * sx, -half + 0.01, half - 0.01)   # ★ 限制在小地图边界内
        c.y = clamp(-dz * sx, -half + 0.01, half - 0.01)  # 北(-z)朝上
    for c in minimap_cells[idx:]:                # 关闭多余格子
        c.enabled = False

    # ---- 2. 保险丝亮点（附近 20 米内，黄色）----
    fi = 0
    for f in list(FUSES):
        if f.is_dead or fi >= len(minimap_marks['fuse']):
            continue
        dx = f.x - player.x
        dz = f.z - player.z
        if math.hypot(dx, dz) > MINIMAP_MARK_RANGE:
            continue
        mark = minimap_marks['fuse'][fi]
        fi += 1
        mark.enabled = True
        mark.x = clamp(dx * sx, -half + 0.015, half - 0.015)
        mark.y = clamp(-dz * sx, -half + 0.015, half - 0.015)
    for mark in minimap_marks['fuse'][fi:]:
        mark.enabled = False

    # ---- 3. 怪物亮点（附近 20 米内，红色）----
    mi = 0
    for m in list(MONSTERS):
        if m.is_dead or mi >= len(minimap_marks['monster']):
            continue
        dx = m.x - player.x
        dz = m.z - player.z
        if math.hypot(dx, dz) > MINIMAP_MARK_RANGE:
            continue
        mark = minimap_marks['monster'][mi]
        mi += 1
        mark.enabled = True
        mark.x = clamp(dx * sx, -half + 0.015, half - 0.015)
        mark.y = clamp(-dz * sx, -half + 0.015, half - 0.015)
    for mark in minimap_marks['monster'][mi:]:
        mark.enabled = False

    # 箭头位于正中央，rotation_z 在 update 中实时绑定玩家 rotation_y


def _hide_minimap(token):
    """1.5 秒后自动隐藏小地图（只隐藏最新一次，防止旧任务误关）"""
    if token == _minimap_token[0]:
        minimap_panel.enabled = False


# =====================================================================================
#  九、危险晕影（Vignette）：屏幕四周暗红边条平滑渐显 + 突脸短促红闪
# =====================================================================================
vignette_bars = []           # [(实体, 强度系数), ...]：上下左右各两层（外浓内淡）
vignette_intensity = 0.0     # 当前晕影强度（向 danger_k 平滑过渡）
scare_flash = None           # 突脸瞬间的短促全屏红闪（0.45 秒内淡出，非常驻大红屏）


def build_vignette():
    """构建暗红晕影：屏幕四周 8 根边条（每边外/内两层，外层更浓形成柔和渐变）。
    替代旧版"粗糙的全屏大红屏"——危险时只有边缘被暗红吞没，中心视野保留。"""
    global scare_flash
    half_w = window.aspect_ratio * 0.5          # UI 半宽（随窗口宽高比）

    def _bar(w, h, x, y, factor):
        e = Entity(parent=camera.ui, model='quad',
                   color=color.rgba(120, 0, 10, 0),
                   scale=(w, h), position=(x, y), z=-0.55)
        vignette_bars.append((e, factor))

    th_o, th_i = 0.085, 0.075                   # 外层/内层厚度
    # 上/下边缘（横条，宽度覆盖任意宽高比）
    _bar(3.2, th_o, 0.0, 0.5 - th_o / 2, 1.0)
    _bar(3.2, th_i, 0.0, 0.5 - th_o - th_i / 2, 0.5)
    _bar(3.2, th_o, 0.0, -0.5 + th_o / 2, 1.0)
    _bar(3.2, th_i, 0.0, -0.5 + th_o + th_i / 2, 0.5)
    # 左/右边缘（竖条，高度覆盖全屏）
    _bar(th_o, 2.2, half_w - th_o / 2, 0.0, 1.0)
    _bar(th_i, 2.2, half_w - th_o - th_i / 2, 0.0, 0.5)
    _bar(th_o, 2.2, -half_w + th_o / 2, 0.0, 1.0)
    _bar(th_i, 2.2, -half_w + th_o + th_i / 2, 0.0, 0.5)
    # 突脸瞬间的短促红闪（很快淡出，不常驻）
    scare_flash = Entity(parent=camera.ui, model='quad',
                         color=color.rgba(150, 0, 0, 0), scale=(3, 2), z=-0.5)


def update_vignette(dt):
    """晕影平滑渐显/渐隐：目标强度 = 最近怪物的危险强度 danger_k（0~1）"""
    global vignette_intensity
    target = danger_k
    vignette_intensity += (target - vignette_intensity) * min(dt * 3.5, 1.0)
    base = int(150 * vignette_intensity)
    if base > 0:
        for e, factor in vignette_bars:
            e.color = color.rgba(120, 0, 10, int(base * factor))
    else:
        for e, factor in vignette_bars:
            e.color = color.rgba(120, 0, 10, 0)


def set_vignette_instant(intensity):
    """立即设置晕影强度（扣命脉冲/死亡时使用，随后仍会平滑回落）"""
    global vignette_intensity
    vignette_intensity = intensity
    base = int(150 * intensity)
    for e, factor in vignette_bars:
        e.color = color.rgba(120, 0, 10, max(0, int(base * factor)))


def reset_vignette():
    """复位晕影与红闪（返回菜单/新局时）"""
    global vignette_intensity
    vignette_intensity = 0.0
    for e, _ in vignette_bars:
        e.color = color.rgba(120, 0, 10, 0)
    if scare_flash is not None:
        scare_flash.color = color.rgba(150, 0, 0, 0)


def _scare_flash_step(alpha):
    """突脸红闪的 invoke 步进（0.45 秒内淡出）"""
    if scare_flash is not None:
        scare_flash.color = color.rgba(150, 0, 0, alpha)


# =====================================================================================
#  十、UI 构建（主菜单 / HUD / 技能面板 / 暂停 / 死亡 / 胜利）
# =====================================================================================
ui_groups = {}
_toast_token = [0]

# 以下 UI 引用在 build_all_ui() 中赋值（函数/更新逻辑按名引用）
toast_text = None
death_text = None
win_text = None
status_text = None
echo_text = None
stamina_fill = None
prompt_text = None
skill_stats_text = None
skill_buttons = {}


def _add_to_group(name, *entities):
    ui_groups.setdefault(name, []).extend(entities)


def show_group(*names):
    """只显示指定组，其余全部隐藏——界面切换天然防穿透"""
    hide_all_ui()
    for name in names:
        for e in ui_groups.get(name, []):
            e.enabled = True


def hide_all_ui():
    for entities in ui_groups.values():
        for e in entities:
            e.enabled = False


def show_toast(message):
    """顶部浮动 UI 提示，2.2 秒后自动消失"""
    _toast_token[0] += 1
    toast_text.text = message
    toast_text.enabled = True
    invoke(_hide_toast, _toast_token[0], delay=2.2)


def _hide_toast(token):
    if token == _toast_token[0]:
        toast_text.enabled = False


def update_status_text():
    """刷新顶部状态条：生命 ×N | 保险丝 n/3"""
    status_text.text = f'生命 ×{player_lives}   保险丝：{collected_fuses}/{FUSES_NEEDED}'


def build_all_ui():
    """构建全部界面实体（初始隐藏，由状态切换函数按组显示）"""
    global toast_text, death_text, win_text, status_text, echo_text
    global stamina_fill, prompt_text, skill_stats_text, skill_buttons

    # ---------------- 顶部浮动提示（常驻） ----------------
    toast_text = Text('', position=(0, 0.42), origin=(0, 0), scale=1.2,
                      color=color.rgb(255, 210, 120), z=-0.75)
    toast_text.enabled = False

    # ================= 主菜单 =================
    menu_title = Text('BLIND HORROR', position=(0, 0.28), origin=(0, 0),
                      scale=3.4, color=color.red, z=-0.05)
    menu_sub = Text('暗 夜 回 声 · 盲 眼 潜 行 · 三 条 命', position=(0, 0.15),
                    origin=(0, 0), scale=1.3, color=color.rgb(170, 170, 170), z=-0.05)
    btn_start = Button(text='开始游戏', position=(0, 0.0), scale=(0.42, 0.075),
                       color=color.rgb(45, 45, 55), on_click=lambda: start_game())
    btn_quit = Button(text='退出游戏', position=(0, -0.11), scale=(0.42, 0.075),
                      color=color.rgb(45, 45, 55), on_click=application.quit)
    for b in (btn_start, btn_quit):
        b.text_entity.color = color.rgb(230, 230, 230)
    menu_help = Text('戴上耳机 · 右键敲击回声视物 · 左键按住潜行 · 收集 3 枚保险丝逃向绿灯',
                     position=(0, -0.28), origin=(0, 0), scale=0.9,
                     color=color.rgb(140, 140, 140), z=-0.05)
    _add_to_group('menu', menu_title, menu_sub, btn_start, btn_quit, menu_help)

    # ================= 局内 HUD =================
    hint_text = Text('WASD移动 | Shift跑 | 左键按住潜行 | 右键回声 | F石头 | E收集 | Tab技能 | Esc暂停',
                     position=window.bottom_left + Vec2(0.015, 0.015),
                     origin=(-0.5, -0.5), scale=0.8, color=color.rgb(160, 160, 160))
    echo_text = Text('回声：就绪',
                     position=window.bottom_left + Vec2(0.015, 0.06),
                     origin=(-0.5, -0.5), scale=0.8, color=color.rgb(90, 160, 220))
    status_text = Text('', position=(0, 0.46), origin=(0, 0), scale=1.1,
                       color=color.rgb(255, 230, 150))
    update_status_text()
    stamina_bg = Entity(parent=camera.ui, model='quad', color=color.rgb(25, 25, 25),
                        scale=(0.64, 0.045), position=(0, -0.44), z=1)
    stamina_fill = Entity(parent=camera.ui, model='quad', color=color.rgb(60, 220, 90),
                          origin=(-0.5, 0), position=(-0.31, -0.44),
                          scale=(0.62, 0.035), z=0.9)
    stamina_label = Text('体力', position=(-0.345, -0.44), origin=(0.5, 0),
                         scale=0.7, color=color.rgb(120, 120, 120))
    prompt_text = Text('— 按 E 收集保险丝 —', position=(0, -0.18), origin=(0, 0),
                       scale=1.1, color=color.rgb(255, 220, 120))
    prompt_text.enabled = False
    _add_to_group('hud', hint_text, echo_text, status_text, stamina_bg, stamina_fill,
                  stamina_label, prompt_text)

    # ================= 局内技能面板（Tab 呼出，全屏遮罩） =================
    skill_mask = Button(model='quad', color=color.rgba(0, 0, 0, 200),
                        scale=(window.aspect_ratio, 1), z=-0.1,
                        on_click=lambda: None)
    skill_panel = Button(model='quad', color=color.rgba(20, 20, 20, 230),
                         scale=(window.aspect_ratio * 0.86, 0.86),
                         position=(0, 0), z=-0.15, on_click=lambda: None)
    skill_title = Text('技 能 面 板', position=(0, 0.36), origin=(0, 0), scale=2.0,
                       color=color.rgb(255, 255, 255), z=-0.2)
    skill_hint = Text('激活消耗 30 体力 · 每局各一次 · 按 Tab 关闭',
                      position=(0, 0.26), origin=(0, 0), scale=0.9,
                      color=color.rgb(170, 170, 170), z=-0.2)
    # 两个技能按钮：动态文字 → 用占位空格创建（★ 防 None 闪退），refresh 再赋真文字
    skill_buttons = {}
    for i, key in enumerate(SKILLS):
        y = 0.1 - i * 0.16

        def _make_activate(k):
            return lambda: click_skill(k)

        btn = Button(text=' ', position=(0, y), scale=(0.78, 0.11),
                     color=color.rgb(90, 25, 25), z=-0.2,
                     on_click=_make_activate(key))
        if btn.text_entity is not None:          # ★ 双保险：text_entity 可能为 None
            btn.text_entity.scale = 0.8
            btn.text_entity.color = color.rgb(255, 255, 255)
        skill_buttons[key] = btn
        _add_to_group('skill', btn)
    skill_stats_text = Text('', position=(0, -0.18), origin=(0, 0), scale=1.0,
                            color=color.rgb(255, 220, 120), z=-0.2)
    skill_close = Button(text='继续游戏（Tab）', position=(0, -0.34),
                         scale=(0.42, 0.07), color=color.rgb(35, 70, 45),
                         z=-0.2, on_click=lambda: resume_game())
    skill_close.text_entity.color = color.rgb(160, 255, 190)
    _add_to_group('skill', skill_mask, skill_panel, skill_title, skill_hint,
                  skill_stats_text, skill_close)

    # ================= 暂停提示 =================
    pause_title = Text('已 暂 停', position=(0, 0.25), origin=(0, 0), scale=2.4,
                       color=color.rgb(230, 230, 230), z=-0.5)
    pause_hint = Text('Esc 继续 | R 重新开始 | Q 返回主菜单',
                      position=(0, 0.1), origin=(0, 0), scale=1.1,
                      color=color.rgb(180, 180, 180), z=-0.5)
    _add_to_group('pause', pause_title, pause_hint)

    # ================= 死亡 / 胜利 =================
    death_text = Text('GAME OVER，按 R 重开\n按 Q 返回主菜单', origin=(0, 0),
                      position=(0, 0.25), scale=2.4, color=color.red, z=-0.7)
    death_text.enabled = False
    win_text = Text('你逃出来了！\nYOU ESCAPED\n按 R 再来一局 | Q 返回主菜单',
                    origin=(0, 0), position=(0, 0), scale=2.0,
                    color=color.rgb(90, 255, 140), z=-0.7)
    win_text.enabled = False


# =====================================================================================
#  十一、游戏流程控制（状态机切换 / 扣命 / 突脸）
# =====================================================================================
def start_game():
    """从主菜单/重开：清理旧场景 → 生成大迷宫 → 进入 PLAYING，重置 3 条命"""
    global game_state, player_lives, collected_fuses
    level_manager.load_level()
    player_lives = START_LIVES                 # ★ 重新开始恢复 3 条命
    collected_fuses = 0                        # 保险丝计数清零
    game_state = GameState.PLAYING
    mouse.locked = True
    show_group('hud')
    minimap_panel.enabled = False             # 确保小地图初始隐藏
    death_text.enabled = False
    win_text.enabled = False
    reset_vignette()                          # 晕影/红闪复位
    prompt_text.enabled = False
    update_status_text()
    echo_text.text = '回声：就绪'
    try:
        if bgm_audio is not None:
            bgm_audio.play()                   # 恐怖 BGM（bgm_horror.mp3，循环）
        if wind_audio is not None:
            wind_audio.play()                  # 持续风声（wind_ambient.mp3，循环）
        if breath_audio is not None:
            breath_audio.play()                # 玩家呼吸声（循环）
        if heartbeat_audio is not None:
            heartbeat_audio.volume = 0.0
            heartbeat_audio.play()             # 心跳循环（音量/频率随距离调节）
    except Exception:
        pass


def back_to_menu():
    """返回主菜单：清理局内世界并停止循环音效"""
    global game_state
    level_manager.teardown()
    game_state = GameState.MENU
    mouse.locked = False
    show_group('menu')
    minimap_panel.enabled = False             # 返回菜单时隐藏小地图
    death_text.enabled = False
    win_text.enabled = False
    reset_vignette()
    try:
        for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio):
            if a is not None:
                a.stop()
    except Exception:
        pass


def pause_game():
    global game_state
    if game_state != GameState.PLAYING:
        return
    game_state = GameState.PAUSED
    mouse.locked = False
    show_group('hud', 'pause')


def resume_game():
    """从技能面板/暂停恢复（重新锁定鼠标）"""
    global game_state
    if game_state not in (GameState.PAUSED, GameState.SKILL_SELECT):
        return
    game_state = GameState.PLAYING
    mouse.locked = True
    show_group('hud')


def open_skill_panel():
    """Tab 呼出技能面板：暂停游戏 + 解锁鼠标 + 刷新技能状态"""
    global game_state
    if game_state != GameState.PLAYING:
        return
    game_state = GameState.SKILL_SELECT
    mouse.locked = False
    refresh_skill_ui()
    show_group('hud', 'skill')


def refresh_skill_ui():
    """刷新技能面板：两个技能按钮的状态（已激活/可激活/体力不足）与玩家状态"""
    if player is not None:
        owned = []
        if player.skill_radar:
            owned.append(SKILLS['radar']['name'])
        if player.skill_silent:
            owned.append(SKILLS['silent']['name'])
        skill_stats_text.text = (
            f'当前体力：{player.stamina:.0f}/{BASE_MAX_STAMINA:.0f}（激活需 30）\n'
            f'生命 ×{player_lives} | 保险丝：{collected_fuses}/{FUSES_NEEDED}\n'
            f'已激活技能：{"、".join(owned) if owned else "无"}')
    for key, btn in skill_buttons.items():
        info = SKILLS[key]
        active = getattr(player, 'skill_radar', False) if key == 'radar' \
            else getattr(player, 'skill_silent', False)
        if active:
            btn.text = f'{info["name"]} —— 已激活 ✓  {info["desc"]}'
            btn.color = color.rgb(30, 80, 45)
            if btn.text_entity is not None:     # ★ 防闪退：text_entity 可能为 None
                btn.text_entity.color = color.rgb(140, 255, 180)
        elif player is not None and player.stamina >= SKILL_COST:
            btn.text = f'{info["name"]} —— 点击激活（耗30体力）  {info["desc"]}'
            btn.color = color.rgb(110, 25, 25)
            if btn.text_entity is not None:
                btn.text_entity.color = color.rgb(255, 255, 255)
        else:
            btn.text = f'{info["name"]} —— 体力不足  {info["desc"]}'
            btn.color = color.rgb(60, 18, 18)
            if btn.text_entity is not None:
                btn.text_entity.color = color.rgb(150, 150, 150)
        if btn.text_entity is not None:
            btn.text_entity.scale = 0.8


def click_skill(key):
    """技能面板按钮点击：尝试激活并刷新 UI 反馈"""
    if game_state != GameState.SKILL_SELECT or player is None:
        return
    if player.activate_skill(key):
        refresh_skill_ui()


def start_jumpscare(monster):
    """触发突脸：怪物瞬移相机正前方 0.5 米 + 尖叫音效 + 短促红闪 + 进入抖动阶段。
    0.7 秒抖动结束后由 update 调用 lose_life() 结算扣命。"""
    global scare_active, scare_timer
    if scare_active or game_state != GameState.PLAYING:
        return
    scare_active = True
    scare_timer = SCARE_DURATION
    monster.play_jumpscare()
    play_sfx('jumpscare', volume=1.0)
    # 短促的全屏红闪（0.45 秒内快速淡出——不是常驻大红屏）
    _scare_flash_step(190)
    invoke(_scare_flash_step, 110, delay=0.15)
    invoke(_scare_flash_step, 50, delay=0.3)
    invoke(_scare_flash_step, 0, delay=0.45)
    print('【突脸】呃啊啊啊啊啊——！！！')


def lose_life():
    """★ 3 条命系统核心：扣 1 命。
    还有剩余生命 → 晕影脉冲式闪红、玩家瞬移回出生点、怪物复位（保留保险丝）；
    生命耗尽 → 进入 DEAD，显示 GAME OVER，按 R 重开。"""
    global player_lives, game_state
    player_lives -= 1
    update_status_text()
    if player_lives > 0:
        # ---- 掉 1 命：晕影猛然涨满再平滑回落、重生、怪物复位，游戏继续 ----
        set_vignette_instant(1.0)              # 红晕脉冲（随后按危险度平滑回落）
        if player is not None:
            player.respawn()                    # 瞬移回出生点（保险丝保留）
        for m in list(MONSTERS):                # 怪物全部重置位置与状态
            if not m.is_dead:
                m.reset()
        print(f'【生命】你被抓住了！剩余生命 ×{player_lives}'
              f'（保险丝 {collected_fuses}/{FUSES_NEEDED} 已保留）')
    else:
        # ---- 3 条命耗尽：GAME OVER ----
        game_state = GameState.DEAD
        mouse.locked = False
        prompt_text.enabled = False
        death_text.enabled = True
        set_vignette_instant(1.0)              # 暗红晕影常驻
        try:
            for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio):
                if a is not None:
                    a.stop()
        except Exception:
            pass
        print('【GAME OVER】三条生命全部耗尽……按 R 重开')


def win_game():
    """集齐保险丝并触碰亮起的绿灯 → WIN"""
    global game_state
    if game_state != GameState.PLAYING:
        return
    game_state = GameState.WIN
    mouse.locked = False
    prompt_text.enabled = False
    win_text.enabled = True
    reset_vignette()
    play_sfx('skill', volume=0.8)
    try:
        for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio):
            if a is not None:
                a.stop()
    except Exception:
        pass


# =====================================================================================
#  十二、全局主循环与输入（Ursina 每帧自动调用）
# =====================================================================================
def update():
    """全局主循环：状态闸门 + 突脸抖动 + 墙体被动线框（平滑）+ 卡墙保护
    + 保险丝指引 + 随机环境音 + 危险晕影/发抖/心跳 + 小地图箭头 + 地面波纹清道夫"""
    global scare_timer, monster_step_timer, buzz_timer, ambient_event_timer, danger_k
    # ★ 防闪退铁律：非 PLAYING 状态一律跳过全部游戏逻辑
    if game_state != GameState.PLAYING:
        return
    if player is None:
        return

    # ---- 0. 突脸阶段：相机高频剧烈抖动（sin(time*50)*0.3），结束后结算扣命 ----
    if scare_active:
        scare_timer -= time.dt
        player.camera_pivot.x = math.sin(pytime.time() * 50) * 0.3    # 剧烈高频抖动
        player.camera_pivot.y = player._base_h + math.sin(pytime.time() * 43) * 0.2
        if scare_timer <= 0:
            scare_active_global_off()
            lose_life()
        return                                    # 突脸期间跳过其它游戏逻辑

    # ---- 1. 清道夫：统一销毁本帧标记 is_dead 的回声球/石头/地面波纹 ----
    for lst in (ECHO_SPHERES, STONES, RIPPLES):
        for obj in list(lst):                   # ★ 浅拷贝遍历
            if getattr(obj, 'is_dead', False):
                lst.remove(obj)
                destroy(obj)

    # ---- 2. 墙体近距感知（★ 平滑不闪烁）：4 米渐显暗灰线框，4.8 米滞回渐隐 ----
    for wall in list(WALLS):
        if wall.is_dead or wall.mode == Wall.MODE_ECHO:
            continue                             # 回声高亮期间不打断
        dx = wall.x - player.x
        dz = wall.z - player.z
        target = 0.0
        if abs(dx) <= WALL_SENSE_EXIT + 2 and abs(dz) <= WALL_SENSE_EXIT + 2:
            d = math.hypot(dx, dz)
            if d <= WALL_SENSE_ENTER:
                target = 1.0                     # 进入 4 米：目标渐显
            elif d <= WALL_SENSE_EXIT and wall.near_alpha > 0.05:
                target = 1.0                     # ★ 滞回带：已亮的墙在 4.8 米内保持
        # 指数逼近（每秒 ~7 次）——渐显渐隐完全平滑，玩家移动不再闪烁
        wall.near_alpha += (target - wall.near_alpha) * min(time.dt * 7.0, 1.0)
        if target == 0.0 and wall.near_alpha < 0.02:
            wall.near_alpha = 0.0
            if wall.mode == Wall.MODE_NEAR:
                wall.set_dark()                  # 完全淡出：恢复近黑实心
            continue
        if wall.mode == Wall.MODE_DARK and wall.near_alpha > 0.04:
            wall.enter_near()                    # 首次越过阈值：开启线框（只切一次）
        if wall.mode == Wall.MODE_NEAR:
            wall.apply_near_alpha(wall.near_alpha)   # 刷新透明度（平滑渐变）

    # ---- 2.5 卡墙保护：玩家中心陷入墙体 → 强行推向开阔地（防穿模卡死）----
    push_out_if_stuck(player)

    # ---- 3. 保险丝：靠近提示 + 10 米内脉动/电流声（救赎的指引）----
    nearest_fuse_d = None
    for f in list(FUSES):
        if f.is_dead:
            continue
        d = dist_xz(player.position, f.position)
        f.near = d <= FUSE_SENSE_RANGE          # 脉动模式开关（Fuse.update 读取）
        if nearest_fuse_d is None or d < nearest_fuse_d:
            nearest_fuse_d = d
    prompt_text.enabled = (nearest_fuse_d is not None and nearest_fuse_d < 1.8)
    if nearest_fuse_d is not None and nearest_fuse_d < FUSE_SENSE_RANGE:
        buzz_timer -= time.dt                   # 微弱的电流"滋滋"声（越近越响）
        if buzz_timer <= 0:
            buzz_timer = 0.55
            k_f = clamp(1 - nearest_fuse_d / FUSE_SENSE_RANGE, 0, 1)
            play_sfx('buzz', volume=0.08 + 0.22 * k_f,
                     pitch=random.uniform(0.9, 1.1))

    # ---- 4. 出口绿灯：触碰判定（未亮起则节流提示）----
    gate = level_manager.exit_gate
    if gate is not None and not gate.is_dead:
        if dist_xz(player.position, gate.position) < 1.6:
            if not gate.locked:
                win_game()
                return
            elif gate.hint_cd <= 0:
                gate.hint_cd = 2.5
                print(f'【出口】绿灯未亮——还差 {FUSES_NEEDED - collected_fuses} 枚保险丝')

    # ---- 5. 最近怪物距离 → 危险晕影/发抖强度 + 心跳渐快渐强 + 沉重脚步 ----
    nearest_m = None
    for m in list(MONSTERS):
        if m.is_dead:
            continue
        d = dist_xz(m.position, player.position)
        if nearest_m is None or d < nearest_m:
            nearest_m = d
    if nearest_m is not None and nearest_m < DANGER_RANGE:
        # 危险强度 0~1（>10 米为 0，逼近击杀距离为 1）：驱动晕影渐显与恐惧发抖
        danger_k = 1 - clamp((nearest_m - KILL_DISTANCE) /
                             (DANGER_RANGE - KILL_DISTANCE), 0, 1)
    else:
        danger_k = 0.0
    update_vignette(time.dt)                    # 暗红晕影平滑渐显/渐隐（边缘，不遮视线）
    if nearest_m is not None and nearest_m < MONSTER_AUDIO_RANGE:
        k = clamp(1 - (nearest_m - KILL_DISTANCE) /
                  (MONSTER_AUDIO_RANGE - KILL_DISTANCE), 0, 1)
        try:
            if heartbeat_audio is not None:
                # ★ 动态心跳：音量随距离增大，播放频率（pitch=速率）随距离加快，
                # 极近时（k→1）pitch 1.4、音量 0.9——极其剧烈
                heartbeat_audio.volume = 0.15 + 0.75 * k
                heartbeat_audio.pitch = 0.8 + 0.6 * k
        except Exception:
            pass
        monster_step_timer -= time.dt
        if monster_step_timer <= 0:
            monster_step_timer = 0.7 - 0.32 * k            # 越近脚步越急促
            play_sfx('monster_step', volume=0.25 + 0.65 * k,
                     pitch=random.uniform(0.9, 1.05))
    else:
        try:
            if heartbeat_audio is not None:
                heartbeat_audio.volume = 0.0
        except Exception:
            pass

    # ---- 6. 随机环境音：滴水 / 远处金属碰撞（8~18 秒随机触发，空旷地下室感）----
    ambient_event_timer -= time.dt
    if ambient_event_timer <= 0:
        ambient_event_timer = random.uniform(8.0, 18.0)
        if random.random() < 0.6:
            play_sfx('drip', volume=0.35, pitch=random.uniform(0.9, 1.15))
        else:
            play_sfx('clang', volume=0.30, pitch=random.uniform(0.85, 1.1))

    # ---- 7. 小地图箭头：旋转实时绑定玩家朝向（地图显示期间）----
    if minimap_panel.enabled and minimap_arrow is not None:
        minimap_arrow.rotation_z = -player.rotation_y

    # ---- 8. UI：回声冷却提示 ----
    echo_text.text = ('回声：就绪 ◆' if player.echo_cooldown <= 0
                      else f'回声冷却…… {player.echo_cooldown:.1f}s')


def scare_active_global_off():
    """结束突脸阶段：复位抖动偏移与全局标记"""
    global scare_active
    scare_active = False
    if player is not None:
        player.camera_pivot.x = 0.0
        player.camera_pivot.y = player._base_h


def input(key):
    """全局按键处理（按状态机分发）"""
    # ---- Esc：暂停 / 继续 / 返回 ----
    if key == 'escape':
        if game_state == GameState.PLAYING:
            pause_game()
        elif game_state in (GameState.PAUSED, GameState.SKILL_SELECT):
            resume_game()
        elif game_state in (GameState.DEAD, GameState.WIN):
            back_to_menu()
        return

    # ---- Tab：呼出 / 关闭局内技能面板 ----
    if key == 'tab':
        if game_state == GameState.PLAYING:
            open_skill_panel()
        elif game_state == GameState.SKILL_SELECT:
            resume_game()
        return

    # ---- 仅 PLAYING 状态：右键回声 / F 石头 / E 收集 ----
    if game_state == GameState.PLAYING and player is not None:
        if key == 'right mouse down':           # 鼠标右键：敲击地面/回声探测
            player.try_echo()
        elif key == 'f':
            player.throw_stone()
        elif key == 'e':
            player.try_pickup()
        return

    # ---- 暂停 / GAME OVER / 胜利状态：R 重开，Q 回主菜单 ----
    if game_state in (GameState.PAUSED, GameState.DEAD, GameState.WIN):
        if key == 'r':
            start_game()
        elif key == 'q':
            back_to_menu()


# =====================================================================================
#  启动
# =====================================================================================
random.seed(pytime.time())      # 用 wall-clock 时间做随机种子（引入 time 的用途）
level_manager = LevelManager()
build_all_ui()
build_minimap()                 # 小地图（默认隐藏，右键敲击时显示 1.5 秒）
build_vignette()                # 暗红晕影（危险时平滑渐显）+ 突脸短促红闪
show_group('menu')              # 从主菜单开始
mouse.locked = False            # 菜单阶段解锁鼠标

print('=' * 56)
print('  BLIND HORROR · 暗夜回声（防穿模·地面波纹版）')
_amb_ok = '✓' if ambient_light is not None else '✗'
_lit_ok = '✓' if lit_shader is not None else '✗（降级为无光照）'
_model_ok = 'monster.obj' if MONSTER_OBJ_PATH else '代码拼凑组合模型'
print(f'  光照：环境光{_amb_ok} + 玩家点光 | lit shader：{_lit_ok} | 近平面 0.15')
print(f'  怪物模型：{_model_ok}')
print(f'  音效：{len(os.listdir(SOUND_DIR)) if os.path.isdir(SOUND_DIR) else 0} 条'
      f'（同目录 mp3/wav 优先，缺失自动合成）| 请戴上耳机')
print('  可选自定义资源：把 bgm_horror.mp3 / wind_ambient.mp3 / monster_scream.mp3')
print('  / heartbeat.wav / jumpscare.mp3 / step_walk.wav / monster.obj 放到游戏目录')
print('=' * 56)

app.run()                       # ★ 启动 Ursina 主循环
