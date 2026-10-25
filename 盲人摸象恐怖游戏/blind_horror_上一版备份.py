# --- Agent 自检与修复报告 ---
# [已修复] 阅读文本交互重构：E 仅阅读（不销毁实体），R 拾取（销毁+记录）。
#          取消 invoke 自动销毁——阅读 UI 保持到玩家手动关闭。
# [已修复] 阅读时怪物不暂停：diary_open 不再阻塞 update/怪物/玩家移动。
#          BGM 降至 30%，按 E/Esc 关闭后恢复。
# [已修复] 怪物 L3 巡逻闪退：_pick_patrol_destination 在 open_points 有限时
#          崩溃 → 改为 open_points 全池兜底选取。
# [已修复] 怪物 SEARCH→PATROL 闪退：SEARCH 结束后 bfs_path(spawn_tile)
#          在 L3 (spawn_tile=None) 崩溃 → if lm.grid 才走 BFS。
# [已修复] 怪物/盲蛛 y 守卫：地下室 (Y=-5) 行走时不会被地面怪物/丝线隔空击杀。
# [已修复] UI 重叠：lose_life 调用 close_diary 强制销毁阅读 UI 后进入死亡。
# [已修复] DIARY_COUNT 硬编码 → 状态栏动态显示日记 ×N。
# [已修复] 3D 音效位置更新：怪物喘息/脚步/AmbientSound3D 每帧 set_audio_position。
# [已修复] 窗口尺寸：window.windowed_size=(1920,1080) 强制大窗口。
# [已检查] 所有 update() 首行均有 entity_gate 或 game_state 过滤 ✓
# [已检查] 列表遍历全部使用 list() 浅拷贝 ✓
# [已检查] safe_destroy 在 destroy 前标记 is_dead 并从列表移除 ✓
# [已检查] 所有 Audio/模型加载均包裹 try-except ✓
# [已检查] 日记/报告 UI 挂载 camera.ui、background=True 自带底板、无碰撞体 ✓
# [已检查] 阅读时按 E 被杀：diary_open 不阻塞怪物/伤害判定，lose_life 正确清理 ✓
#
# ★★ F11 切换全屏（任何状态均可按）
# ★★ 音频文件清单（放入 assets/sounds/ 即自动启用；缺失时合成兜底）
#    bgm_horror.mp3 / wind_ambient.mp3 / monster_scream.mp3 / heartbeat.wav /
#    jumpscare.mp3 / step_walk.wav / taunt_1~4.wav / sfx_door_open.mp3 /
#    sfx_door_close.mp3 / sfx_clock_tick.mp3 / ambient_thunderstorm.mp3 /
#    sfx_water_drip.mp3 / bgm_random_1~3.mp3 / sfx_scare_whisper.mp3 /
#    sfx_scare_thunder.mp3 / sfx_scare_scream.mp3 / sfx_scare_metal.mp3
# ★★ 怪物模型 assets/models/model_monster.obj（.glb 优先）
# --- Agent 自检与修复报告结束 ---

from ursina import *          # 第一行：Ursina 游戏引擎（安装：pip install ursina）
import random                 # 迷宫 DFS / 随机打墙 / 怪物游荡 / 随机词条与嘲讽
import math                   # 角度、距离、抖动、晕影与音效波形合成
import time as pytime         # 规格要求引入 time；别名避免覆盖 Ursina 自带 time（time.dt）
import os                     # 脚本目录 / 资源与音效文件管理
import shutil                 # 复制系统中文字体到游戏目录
import wave as _wave_mod      # 用代码合成 wav 音效（无外部素材也能出声）
import struct                 # wav 采样点打包
import json                   # 局外技能树（代币/永久技能）本地存档
import ctypes                  # ★ DPI 感知修复（防止窗口变小或模糊）
import urllib.request         # 尝试从网络直链下载音效与怪物 .obj 模型（全部 try-except 兜底）
import textwrap                # ★ 规格一.1：档案库长文本按行截断换行

# ★ 三重自检前置：stdout/stderr 统一 UTF-8——✅/❌ 日志符号不在 GBK 编码内，
#   输出被重定向到文件时防止 UnicodeEncodeError 闪退（铁律：绝不闪退）。
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# =====================================================================================
#  BLIND HORROR · 暗夜回声 —— 3D 第一人称盲人恐怖潜行游戏
# -------------------------------------------------------------------------------------
#  ★★ 按 T 切换全屏(1920×1080) / 半屏(1280×720)（任何状态下均可按）
#  ★★ 音频文件清单（全部放入 assets/sounds/ 即自动启用；缺失时自动使用代码
#     合成音效或静音运行，绝不报错中断）：
#     ① bgm_horror.mp3           —— 背景音乐（循环）
#     ② wind_ambient.mp3         —— 环境风声（循环）
#     ③ monster_scream.mp3       —— 怪物追击嘶吼
#     ④ heartbeat.wav            —— 心跳声（循环，音量随距离变化）
#     ⑤ jumpscare.mp3            —— 突脸尖叫
#     ⑥ step_walk.wav            —— 行走脚步
#     ⑦ taunt_1.wav ~ taunt_4.wav —— 死亡嘲讽英文男声 ×4
#     ⑧ sfx_door_open.mp3        —— 开门声
#     ⑨ sfx_door_close.mp3       —— 关门声
#     ⑩ sfx_clock_tick.mp3       —— 时钟滴答（监控室 3D 循环）
#     ⑪ ambient_thunderstorm.mp3  —— 雷雨环境（循环）
#     ⑫ sfx_water_drip.mp3        —— 水滴声（停尸房 3D 循环）
#     ⑬ bgm_random_1.mp3 ~ 3.mp3  —— 随机 BGM ×3（每次进关随机选一首）
#     ⑭ sfx_scare_whisper.mp3     —— 随机惊吓：耳语
#     ⑮ sfx_scare_thunder.mp3     —— 随机惊吓：远雷
#     ⑯ sfx_scare_scream.mp3      —— 随机惊吓：尖叫
#     ⑰ sfx_scare_metal.mp3       —— 随机惊吓：金属
#     ⑱ models/model_monster.obj  —— 怪物模型（放 assets/models/ 下）
# =====================================================================================
# -------------------------------------------------------------------------------------
#  ★ 背景：你是盲女伊芙琳（Evelyn），被困于一座废弃的地下研究所。
#
#  本版修复重点：
#    1.【柜子透孔观察】柜子由多块薄板拼成（两扇门中间留竖直门缝），钻入后摄像机向
#      柜门平滑前推卡在门缝处；屏幕四周纯黑遮罩只留中间一条竖缝+横缝——透过柜门
#      缝隙偷窥外面的怪物，而不是完全黑屏。碰撞体留在柜内，怪物无法发现。
#    2.【局外 UI 排版】觉醒/关卡选择等所有面板：文字 z 层级高于背景面板（前景更
#      负），背景统一深色半透明 rgba(20,20,20,200)，文字亮白/血红高对比；
#      关卡名字号收敛（text scale 1.0），长文本拆分为副标题小字，不再溢出按钮。
#    3.【楼梯与多层地形】台阶=带 BoxCollider 的立方体 + 解析斜坡；玩家 update 用
#      射线检测脚下地形，y 坐标 lerp(y, target, dt*10) 平滑上下——不用物理引擎。
#      第二关：出生高台(下行楼梯) + 真实出口高台(上行楼梯)。
#    4.【屏息系统】Q 由 input 事件驱动 is_holding_breath（'q'按下 / 'q up'松开）；
#      每秒耗氧 25 点且完全静音；耗尽→沉重喘息巨响+10 秒疲惫期；
#      蓝色氧气条仅在屏息时显示（松开/耗尽即隐藏）。
#
#  状态机 game_state（5 态）：'MENU' | 'PLAYING' | 'PAUSED' | 'DEAD' | 'WIN'
#    （关卡选择 / 技能觉醒 / 设置 为主菜单子面板，不占状态机）
#
#  保留核心机制：回声定位（线框球+地面声呐圆环+青白高亮 1.5s）、怪物寻路 AI 与
#  突脸（黑白特写+英文男声嘲讽）、3D 环绕音效尝试、小地图（朝向箭头/墙/保险丝/
#  怪物）、屏息、多层楼梯、随机词条、代币技能树、3 条命（复活保留进度）。
#
#  防闪退铁律（贯穿全文件）：
#    1) 所有实体 update() 第一行：if game_state != GameState.PLAYING: return
#    2) 遍历实体列表一律 for obj in list(target_list): 浅拷贝
#    3) 销毁顺序：is_dead=True → 判定中过滤 → 从列表 remove() → destroy()；
#       任何 destroy 前都有 None / is_dead 检查，杜绝空指针
#    4) 一切资源加载（文件/网络/3D 音频）全部 try-except + 超时，失败静默降级
#
#  ★★ 支持的外部音频文件（全部放入 assets/sounds/ 即自动启用；缺失时自动使用
#     代码合成音效或静音运行，绝不报错中断）：
#     ① sfx_door_open.mp3        —— 开门声（推拉门按 E 开门 / 平移动画时播放）
#     ② sfx_door_close.mp3       —— 关门声（推拉门自动/手动关闭时播放）
#     ③ sfx_clock_tick.mp3       —— 时钟滴答（监控室中心的 3D 循环环境音）
#     ④ ambient_thunderstorm.mp3 —— 雷雨环境（进入关卡后循环播放的全局环境音）
#     ⑤ sfx_water_drip.mp3       —— 水滴声（停尸房角落的 3D 循环环境音）
#
#  ★★ 本轮新增的 7 个随机音频文件（放入 assets/sounds/ 即自动启用；缺失时
#     print 提示并静音/回退合成 BGM，绝不报错中断）：
#     ⑥ bgm_random_1.mp3         —— 随机 BGM 之一 ┐
#     ⑦ bgm_random_2.mp3         —— 随机 BGM 之二 ├ 每次进入关卡随机选一首
#     ⑧ bgm_random_3.mp3         —— 随机 BGM 之三 ┘ 循环播放（loop=True）
#     ⑨ sfx_scare_whisper.mp3    —— 随机惊吓：耳语 ┐
#     ⑩ sfx_scare_thunder.mp3    —— 随机惊吓：远雷 │ 每 15~45 秒随机触发一次，
#     ⑪ sfx_scare_scream.mp3     —— 随机惊吓：尖叫 │ 以 is_3d=True 在玩家周围
#     ⑫ sfx_scare_metal.mp3      —— 随机惊吓：金属 ┘ 15~30 米随机位置发出
#
#  运行：  pip install ursina  →  python blind_horror.py
# =====================================================================================


# =====================================================================================
#  ★ 标准化项目目录结构（规格：在游戏初始化 app = Ursina() 之前自动创建，防止报错）：
#      assets/sounds/    —— 全部音频文件（.mp3 / .wav）
#      assets/models/    —— 怪物模型（model_monster.obj）
#      assets/textures/  —— 贴图（预留目录，当前版本未使用贴图）
#    使用 SCRIPT_DIR 锚定的绝对路径 + 规格要求的相对路径双重创建：
#    无论从哪个工作目录启动（双击 .bat / 命令行），目录都会建在游戏旁边。
# =====================================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))    # 游戏代码所在目录
ASSETS_DIR = os.path.join(SCRIPT_DIR, 'assets')            # ★ 标准资源根目录
SOUND_DIR = os.path.join(ASSETS_DIR, 'sounds')             # ← 所有 Audio() 路径的根
MODEL_DIR = os.path.join(ASSETS_DIR, 'models')             # ← 怪物模型路径的根
TEXTURE_DIR = os.path.join(ASSETS_DIR, 'textures')         # ← 贴图路径的根（预留）
os.makedirs('assets/sounds', exist_ok=True)      # 规格要求的相对路径创建
os.makedirs('assets/models', exist_ok=True)
os.makedirs('assets/textures', exist_ok=True)
os.makedirs(SOUND_DIR, exist_ok=True)            # 绝对路径再建一次（工作目录不同也安全）
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(TEXTURE_DIR, exist_ok=True)
SAVE_PATH = os.path.join(SCRIPT_DIR, 'meta_save.json')


def migrate_legacy_assets():
    """一次性迁移：把旧版 sounds/ 与 models/ 里的资源文件复制到 assets/ 对应目录。
    只复制、不删除旧文件（迁移失败静默跳过——旧文件仍在原处，不影响运行）。"""
    pairs = ((os.path.join(SCRIPT_DIR, 'sounds'), SOUND_DIR),
             (os.path.join(SCRIPT_DIR, 'models'), MODEL_DIR))
    for src, dst in pairs:
        try:
            if not os.path.isdir(src):
                continue
            os.makedirs(dst, exist_ok=True)
            for fn in os.listdir(src):
                s, d = os.path.join(src, fn), os.path.join(dst, fn)
                if os.path.isfile(s) and not os.path.exists(d):
                    shutil.copy2(s, d)
        except Exception:
            continue                    # 迁移失败不影响游戏（合成音效会自动补齐）


migrate_legacy_assets()


# =====================================================================================
#  ★ 外部全本故事文件生成（规格二.1）
#    游戏启动时如果 Full_Lore.txt 不存在，则自动创建并写入完整背景故事（约 1000 字）。
#    ★ 游戏内的任何 UI 都不允许读取这个文件——它只作为玩家通关后的"阅读奖励"。
# =====================================================================================
FULL_LORE_PATH = os.path.join(SCRIPT_DIR, 'Full_Lore.txt')

FULL_LORE_CONTENT = """\
═══════════════════════════════════════════════
  BLIND HORROR · 完整背景故事（通关后阅读）
  以下内容包含剧透，建议通关后阅读。
═══════════════════════════════════════════════

【序章 · 静默穹顶】

"静默穹顶"是一项始于 1987 年的绝密军事感知增强计划。
其核心理念是：剥夺人类视觉后，大脑为了生存会重新分配
神经资源，将听觉放大到超乎想象的程度。项目负责人佩雷
斯医生在立项书上写道："上帝关闭一扇门，我们打开深渊。"

【第一章 · 伊芙琳】

伊芙琳·克劳斯，28 岁，先天性情感受损者。她在知情同意
书上签下了自己的名字——那份文件被伪装成了一份"视觉
神经捐赠协议"。实际上，她的视觉皮层被逐步切除，空出的
神经通道被用来自 7 号实验体的听觉组织填充。

手术"成功"了。伊芙琳失明了，但她获得了远超常人的听觉。
她能听到两个房间外的滴水声、墙壁里的电流声、以及地下
某处很轻很轻的呼吸声。

没有人告诉她，那呼吸声来自什么。

【第二章 · 七号实验体】

7 号实验体的真名是埃利奥特·克劳斯——伊芙琳的亲哥哥，
前首席神经研究员。他自愿进入了"静默穹顶"实验舱，成为
第一批人体试验对象。

穹顶里的日子是地狱。40 天的绝对寂静让他的精神几乎崩
溃，但他的听觉确实被强化到了不可思议的程度。当他最终
走出穹顶时，他的眼睛完好无损——却再也看不见任何东西。
视觉皮层已经被手术切除，准备移植给下一个"志愿者"。

那个志愿者就是他的妹妹。

【第三章 · 崩溃】

埃利奥特被编号为"7 号实验体"，关押在 B 区隔离室。他
拒绝进食，拒绝配合，反复用头撞击墙壁。研究人员记录道：
"受试体表现出极端的攻击性和不可预测性。"

但没人注意到，他每天晚上都会安静下来——因为他听得见
妹妹的心跳。整个研究所里，只有那道心跳不害怕。

第 63 天，研究所停电。备用电源启动需要 90 秒。在那 90
秒里，埃利奥特挣脱了约束。

他没有攻击任何人。他只是沿着走廊，凭声音找到了佩雷斯
医生的办公室。然后，他撕开了通往地面的最后一道门。

【第四章 · 撤离与沉没】

研究所紧急撤离。混乱中，伊芙琳被落下了。她是一个盲人，
在没有引导的情况下无法走出地下迷宫。

她没有哭。她听着整座研究所安静下来，然后听见哥哥挣脱
束缚的声音——金属撕裂、混凝土碎裂、还有那不再属于人类
的嘶吼。

它在这下面。它在听。

【终章 · 暗夜回声】

多年以后，这座废弃的研究所成了城市传说。有人说地下室
里住着一个看不见的东西，它会追逐一切发出声音的猎物。
也有人说，在极深的夜里，你能听见一个女人用拐杖敲打地
面——不是求救的信号，而是在给那东西引路。

它们都错了。伊芙琳没有疯。她在等。

等哥哥记起她的声音。

═══════════════════════════════════════════════
  BLIND HORROR · 完
  感谢游玩。请戴上耳机，重新听一遍那些声音。
═══════════════════════════════════════════════
"""


def generate_full_lore():
    """★ 规格二.1：启动时检查 Full_Lore.txt 是否存在，不存在则创建并写入全本故事。
    游戏内的任何 UI 都不允许读取这个文件——仅供玩家通关后手动阅读。"""
    try:
        if not os.path.exists(FULL_LORE_PATH):
            with open(FULL_LORE_PATH, 'w', encoding='utf-8') as f:
                f.write(FULL_LORE_CONTENT)
            print('（已生成 Full_Lore.txt——完整背景故事，通关后阅读）')
    except Exception as e:
        print(f'（Full_Lore.txt 生成失败，不影响游戏：{e}）')


generate_full_lore()


# =====================================================================================
#  ★ 音频文件路径排查（规格一.1）：启动时遍历检查所需音频文件，
#    缺失的用醒目前缀打印告警，让用户知道哪些文件需要补充。
#    不阻塞游戏——合成音效会自动补齐。
# =====================================================================================
AUDIO_CHECKLIST = [
    ('bgm_horror.mp3',           '背景音乐'),
    ('wind_ambient.mp3',         '环境风声'),
    ('monster_scream.mp3',       '怪物嘶吼'),
    ('heartbeat.wav',            '心跳声'),
    ('jumpscare.mp3',            '突脸尖叫'),
    ('step_walk.wav',            '行走脚步'),
    ('sfx_door_open.mp3',        '开门声'),
    ('sfx_door_close.mp3',       '关门声'),
    ('sfx_clock_tick.mp3',       '时钟滴答'),
    ('ambient_thunderstorm.mp3', '雷雨环境'),
    ('sfx_water_drip.mp3',       '水滴声'),
    ('bgm_random_1.mp3',         '随机 BGM 1'),
    ('bgm_random_2.mp3',         '随机 BGM 2'),
    ('bgm_random_3.mp3',         '随机 BGM 3'),
    ('sfx_scare_whisper.mp3',    '惊吓：耳语'),
    ('sfx_scare_thunder.mp3',    '惊吓：远雷'),
    ('sfx_scare_scream.mp3',     '惊吓：尖叫'),
    ('sfx_scare_metal.mp3',      '惊吓：金属'),
]


def check_audio_files():
    """★ 规格一.1：启动时遍历检查音频文件，缺失的打印红色醒目告警。
    不阻塞游戏——合成音效会自动补齐。"""
    missing = 0
    for fn, desc in AUDIO_CHECKLIST:
        path = os.path.join(SOUND_DIR, fn)
        if not os.path.exists(path):
            missing += 1
    if missing:
        print(f'\033[91m[警告] 音频排查：{missing}/{len(AUDIO_CHECKLIST)} 个外部音频文件'
              f'未找到——将使用代码合成音效兜底，游戏正常运行。\033[0m')
    else:
        print('（音频排查：全部外部音频文件就绪 ✓）')


check_audio_files()


# ★ DPI 感知修复（规格一.2）：防止 Windows 高 DPI 环境下窗口变小或模糊
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ★ Ursina 应用必须先于任何实体创建（文末 app.run() 启动主循环）
app = Ursina(title='BLIND HORROR · 暗夜回声')

# ★ 规格一（顺序关键）：先 default_resolution 后 default_font——
#   字体图集在加载瞬间按当时的 default_resolution 生成，先字体后分辨率
#   会得到拉长/巨大的字形且无法追溯修复。此块位于任何 Text 创建之前。
Text.default_resolution = 1080 * Text.size
try:
    Text.default_font = 'msyh.ttc'          # 微软雅黑（缺失时 setup_cjk_font 兜底）
except Exception:
    pass

# ----------------------------- ★ 窗口初始化修复（规格一/二，最高优先级） -----------------------------
# 问题：本机 Panda3D 会把浮点的 windowed_size 写进配置（win-size 2048.0 1152.0 →
# "Invalid integer value" 告警），叠加部分显卡/远程桌面的 "No primary monitor
# found"，窗口可能以异常尺寸创建或跑到屏幕外——表现为"程序已启动但看不到窗口"。
# 修复：app = Ursina() 之后立即强制整数尺寸与初始位置（规格要求的两行），
# 全程 try-except + Panda3D 原生 WindowProperties 兜底，保证窗口可见。
try:
    window.windowed_size = (1920, 1080)  # ★ 规格三：强制大窗口
    window.fullscreen = False
    window.borderless = False
    window.position = (50, 50)
    print('✅ 窗口初始化: 1920×1080（DPI 感知已开启 · 近裁剪面 0.05 防穿墙）')
except Exception:
    try:
        window.size = (1920, 1080)
        window.position = (50, 50)
    except Exception as e:
        print(f'（提示：窗口尺寸设置失败，使用引擎默认值：{e}）')

# ----------------------------- 摄像机近裁剪面优化（防穿墙透视） -----------------------------
# ★ 规格一.1：近裁剪 0.1（贴墙不再切穿看到隔壁房间）+ 远裁剪 100
#   （纯黑环境下 100 米外的物体本来就不可见，远裁剪不影响体验）
try:
    camera.near_clip = 0.05         # ★ 规格五.1：近裁剪 0.05（贴墙防透视）
    camera.far_clip = 100
except Exception:
    pass
try:
    base.camLens.set_near(0.05)     # Panda 底层兜底（与上面等值，双保险）
    base.camLens.set_far(100.0)
except Exception:
    pass

# ----------------------------- 核心环境：极暗氛围（非纯黑） -----------------------------
window.color = color.rgb(5, 5, 5)      # ★ 极致黑暗（规格：5,5,5）
scene.fog_color = color.black           # ★ 规格三：黑色浓雾
scene.fog_density = 0.1                  # ★ 密度 0.1——稍远即迅速隐入黑暗

# ★ 规格一.1：环境光压至极低（5,5,5）——仅防纯黑死寂，不提供可读性
try:
    ambient_light = AmbientLight(color=color.rgb(5, 5, 5))
except Exception:
    ambient_light = None

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
    window.fps_counter.enabled = False
    window.exit_button.enabled = False
except Exception:
    pass

# （SCRIPT_DIR / SOUND_DIR / MODEL_DIR / SAVE_PATH 已在 app = Ursina() 之前定义——
#   全部指向标准化的 assets/ 目录结构，此处不再重复定义）


def setup_cjk_font():
    """加载系统中文字体（复制到游戏目录用相对路径加载，实测可靠）；失败静默回退。"""
    for name in ('msyh.ttc', 'simhei.ttf', 'wqy-microhei.ttc', 'PingFang.ttc'):
        if os.path.exists(os.path.join(SCRIPT_DIR, name)):
            try:
                Text.default_font = name
                print(f'✅ 中文字体生效: {name}')
                return name
            except Exception:
                pass
    for src in ('C:/Windows/Fonts/msyh.ttc',
                'C:/Windows/Fonts/simhei.ttf',
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                '/System/Library/Fonts/PingFang.ttc'):
        if not os.path.exists(src):
            continue
        try:
            shutil.copy2(src, SCRIPT_DIR)
            Text.default_font = os.path.basename(src)
            print(f'✅ 中文字体生效: {os.path.basename(src)}（已从系统字体目录复制）')
            return os.path.basename(src)
        except Exception:
            continue
    print('\033[91m❌ 严重警告: 未找到可用中文字体（msyh.ttc/simhei.ttf），回退引擎默认渲染\033[0m')
    return None


setup_cjk_font()

# ★ 规格修复（一.1，最高优先级）：初始化时设定默认文字分辨率——
#   加载 simhei.ttf 等自定义中文字体后，若缺这一行，字体内建的巨大分辨率
#   会让所有 Text/Button 文字渲染得异常放大（主菜单字体过大的元凶）。
#   try-except 包裹：旧版本引擎属性缺失时不影响运行。
try:
    Text.default_resolution = 1080 * Text.size
except Exception as e:
    print(f'（提示：Text.default_resolution 设置失败，不影响运行：{e}）')

# =====================================================================================
#  一、全局状态机与数值策划表
# =====================================================================================
class GameState:
    """游戏全局状态机（7 态）：含独立的技能觉醒状态。
    设置仍为主菜单子面板（open 标志管理），防穿透遮罩齐全。"""
    MENU = 'MENU'                  # 主菜单（含设置子面板）
    LEVEL_SELECT = 'LEVEL_SELECT'  # 关卡选择
    PLAYING = 'PLAYING'            # 游玩中（唯一执行游戏逻辑的状态）
    PAUSED = 'PAUSED'              # 暂停
    DEAD = 'DEAD'                  # 生命耗尽 → GAME OVER（黑白化+嘲讽）
    WIN = 'WIN'                    # 通关


game_state = GameState.MENU

# ---------------- 迷宫 ----------------
GRID_L1 = 40                # 第一关：40x40 地块（160x160 米）
GRID_L2 = 30                # 第二关：30x30 地块（120x120 米）
BRAID_RATIO = 0.18          # 随机打墙比例：制造环路与十字路口
TILE = 4.0
WALL_HEIGHT = 4.0

# ---------------- 玩家 ----------------
WALK_SPEED = 4.5
RUN_MULT = 1.8
SNEAK_MULT = 0.5
STAND_HEIGHT = 1.8          # 视点高度（相对脚底）
PLAYER_RADIUS = 0.5
BASE_MAX_STAMINA = 100.0
RUN_DRAIN_PER_FRAME = 0.5   # 奔跑每帧耗 0.5 体力（×60×dt 帧率无关化）
REGEN_NORMAL = 10.0
REGEN_SNEAK = 18.0
WALK_NOISE = 10.0
RUN_NOISE = 20.0
ALL_MONSTERS = 1.0e9
ECHO_NOISE_RADIUS = 25.0    # ★ 规格四.1：回声敲击噪音半径 25（无视楼层 Y）
# ---- 屏息系统 ----
O2_MAX = 100.0              # 氧气上限
O2_DRAIN = 25.0             # ★ 屏息每秒耗氧 25 点（规格值，约 4 秒耗尽）
O2_REGEN = 20.0             # 非屏息每秒回氧（缓慢恢复）
GASP_NOISE = 15.0           # 氧气耗尽的强制喘息噪音半径（规格：15）
BREATH_EXHAUST = 10.0       # 耗尽后的疲惫期（秒，期间无法屏息）
SNEAK_BREATH_NOISE = 3.0    # 潜行时呼吸可被近距怪物听到的半径（屏息可消除）
# ---- 楼梯/地形 ----
GROUND_LERP_SPEED = 10.0    # ★ 玩家 y 平滑插值速度（规格：lerp(y, target, dt*10)）
CAM_PEEK_Z = -0.55          # ★ 柜内窥视：摄像机向柜门方向前推量（本地 -z 为面前）

# ---------------- 回声 / 投掷 / 收集 ----------------
ECHO_COOLDOWN_BASE = 5.0    # ★ 回声基础冷却 5 秒（规格；觉醒·强化回声 -1.5 秒）
ECHO_STAMINA_COST = 10.0
ECHO_DURATION = 1.5
ECHO_MAX_RADIUS = 30.0
ECHO_MAX_SCALE = 60.0
REVEAL_DURATION = 8.0       # ★ 回声高亮持续 8 秒（规格：期间缓慢淡出，绝不瞬间熄灭）
STONE_SPEED = 16.0
STONE_LIFE = 1.5
STONE_GRAVITY = 1.5
STONE_COOLDOWN = 3.0
STONE_NOISE = 50.0          # ★ 规格四.2：石头落地噪音半径 50（全图）
PIPE_NOISE = 50.0           # ★ 规格四.2：管子落地噪音半径 50（全图，怪物立刻 CHASE）
WEB_NOISE = 25.0            # ★ 规格四.3：白丝撕裂噪音半径 25
# ---- ★ 盲蛛重构：地面白丝陷阱（规格）----
ONLY_SPIDERS = False        # ★ 规格二：怪物生态分级启用——聆听者/盲蛛实体/白丝/乌鸦并存
WEB_COUNT = 6               # 每关白丝陷阱数量（规格：6 个）
WEB_HALF_WIDTH = 1.5        # 白丝宽度（约半条路，绝不封死通道——可绕行）
WEB_TRIGGER_DIST = 1.2      # 踩中判定半径（米）
WEB_SLOW_DURATION = 3.0     # 踩中减速持续时间（秒）
WEB_SLOW_MULT = 0.4         # 减速乘数（速度降低 60%）
WEB_COOLDOWN = 5.0          # 触发后白丝失效期（秒，期间变灰防重复触发）
SPIDER_LEG_LEN = 4.6        # 蛛腿长度（底端从天花板 Y=4 一插到地面）
FUSES_NEEDED = 3
DIARY_COUNT_L2 = 3          # 第二关日记数量（蓝色微光）

# ---------------- 怪物 / 突脸 / 危险反馈 ----------------
KILL_DISTANCE = 1.2
MONSTER_CHASE_SPEED = WALK_SPEED * RUN_MULT * 1.2   # ★ 追击速度 = 玩家奔跑速度 × 1.2（规格）
MONSTER_PATROL_SPEED = 1.6
MONSTER_AUDIO_RANGE = 8.0
DANGER_RANGE = 10.0
SCARE_DURATION = 0.7
SCARE_DIST = 0.5

# ---------------- 被动感知 ----------------
WALL_SENSE_ENTER = 4.0
WALL_SENSE_EXIT = 4.8
FUSE_SENSE_RANGE = 10.0

# ---------------- 小地图 ----------------
MINIMAP_VIEW = 20.0
MINIMAP_MARK_RANGE = 20.0
MINIMAP_SIZE = 0.34
MINIMAP_CELL_POOL = 130

# =====================================================================================
#  ★ 人物人设字典（CHARACTER_PERSONAS，规格三）——写死于代码中。
#    【约束声明】后续所有生成的剧情文本（日记 / 实验报告 / 档案长文），
#    必须严格符合以下人设，不得出现人设冲突的内容。
# =====================================================================================
CHARACTER_PERSONAS = {
    'evelyn': {
        'name': '伊芙琳（主角）',
        'persona': '失忆，前实习研究员，因基因改造致盲；敏感、恐惧，'
                   '但听觉极其敏锐——她能在绝对黑暗里靠回声"看见"声音的形状。',
    },
    'director': {
        'name': '主管',
        'persona': '冷酷，狂热追求"静默穹顶"进化论——坚信黑暗不是缺陷而是'
                   '进化留的一扇门；视失败品为草芥，视人类为可计价的消耗品。',
    },
    'junior_researcher': {
        'name': '初级研究员（陈明远）',
        'persona': '有道德挣扎，对伊芙琳抱有同情；屡次上书反对"褪去视觉"方案，'
                   '最终被灭口（"调岗"之后再无人见过他）。',
    },
    'mutant': {
        'name': '变异体（主怪前身 · 7 号）',
        'persona': '曾经是热爱音乐的普通人（伊芙琳的哥哥埃利奥特）；在极度痛苦中'
                   '听觉被放大到病态，最终彻底疯狂——但仍有残存的、寻找妹妹的执念。',
    },
}

# ---------------- 局外：残存记忆档案库（规格二，10 段 ×300+ 字）----------------
START_LIVES = 3
# ★ 十段残片互相关联却故意互相矛盾、互相留白——拼不出完整的真相。
LORE_ARCHIVE = [
    {'title': '残存记忆 · 一｜醒来（伊芙琳的自白）',
     'text': '我在黑暗里醒来。不是夜晚的那种黑——是连"黑"这个概念都不存在的黑。'
             '我伸手摸自己的脸，指尖碰到的是缠满纱布的额头和一只冰冷的金属环。'
             '我喊，声音撞在墙上又弹回来，像有人学我说话。我想不起自己的名字，'
             '想不起家，想不起任何一张脸。只有一个词固执地浮上来：伊芙琳。是我吗？'
             '我不知道。墙上有刻痕，七道，深浅不一——是数日子的吗？数到七，然后呢？'
             '门缝底下有光，一晃一晃，像有人在走廊里提着灯慢慢地走。我屏住呼吸。'
             '灯停在了我的门口。这一刻我发现，比起失明，我更害怕的是：'
             '我居然已经习惯了这种害怕。'
             '更可怕的是：我昨天在墙上摸到了别人的字迹，比我的刻痕旧得多——'
             '"别相信耳朵"。如果我以前认识写字的人，为什么我一个都想不起来？'},
    {'title': '残存记忆 · 二｜水母（伊芙琳的自白）',
     'text': '他们说我以前看得见。这个词像一颗坏掉的牙，一碰就疼。看。见。'
             '我闭上眼睛努力去想颜色，脑子里却只有声音的形状：水滴是尖的，'
             '风是软的，脚步声有脚趾的重量。检查的时候医生让我摸盲文，'
             '我摸出来的第一个词是"样本"。我说这不是我的名字，'
             '他停了一下，翻纸的声音很慌。还有一件事我没告诉任何人：'
             '每天凌晨，我都能听见很远的地方有水声，哗啦，哗啦，'
             '像很多人在很深的水里一起挣扎。我把耳朵贴在墙上，'
             '水声就变成了敲击——三短，三长，三短。我不知道那是什么意思，'
             '但我把它刻在了墙上，刻在七道痕的旁边。'
             '还有，敲击声最近变了。它不再等我回应，而是数着我的呼吸——'
             '我吸，它停；我吐，它敲。墙那边的东西，学得越来越像我。'
             '我今天试着回敲了三下。之后一整天，再没有任何声音。'
             '安静得像它在憋着什么。'},
    {'title': '内部邮件 · 三｜关于"褪去视觉"方案的正式异议',
     'text': '收件人：项目伦理委员会。发件人：初级研究员 陈明远。'
             '主题：关于"褪去视觉"方案 T-7 的正式异议。各位委员：我反对继续执行 T-7。'
             '所谓褪去视觉，并非摘除眼球——摘除反而是仁慈的。方案是向视神经注射'
             '纤维化药剂，让受试者在三到六个月里"看着"自己的视野一点点被侵蚀：'
             '先失去颜色，再失去形状，最后连光感都会变成疼痛。全程受试者意识清醒。'
             '我们管这叫数据采集，我管这叫凌迟。七号候选人的家属签字存在涂改痕迹，'
             '我申请调阅原始文件，被驳回。如果委员会坚持推进，请至少把我的反对意见归档'
             '——总有一天会有人翻出来，证明我们中间不是所有人都装聋。'
             '另：昨晚 B 区的灯又灭了十二分钟。停电期间，'
             '地下三层的通风系统仍在运转——是谁在维护它？'
             '委员会里没有人回答这个问题，他们只是更快地批完了下一阶段的经费。'},
    {'title': '内部邮件 · 四｜回复：异议已归档',
     'text': '收件人：陈明远。发件人：项目管理部。主题：回复：关于 T-7 的异议。'
             '陈研究员：你的异议已归档，编号 0449，感谢你的"职业热情"。现通知如下：'
             '一、T-7 已于昨夜完成，进程比预期顺利。二、关于你调阅 7 号家属签字的申请'
             '——不存在所谓涂改，那是更正。三、你将不再参与 T 系列项目，'
             '请于本周内完成工作交接。另：你上个月申请调阅的 7 号个人档案我们看过了，'
             '他妹妹的入组志愿书和你联想的"人情故事"没有关系。科学不需要你们的同情心。'
             '科学需要的是：一个能在绝对黑暗里靠耳朵活着的人。——项目管理部'
             '（此邮件已抄送主管办公室）'
             '又及：你上次问"7 号的妹妹为什么也在名单上"。答案很简单：'
             '样本需要对照组。至于对照组意味着什么——'
             '这不是你需要担心的事，陈研究员。管好你自己的耳朵。'},
    {'title': '病患日记 · 五｜光在退潮（302 床 阿彻）',
     'text': '我叫阿彻，302 床。医生说我的眼睛是"渐暗型"：像退潮，每天退一点。'
             '上个月我还能看见走廊尽头的绿灯，这个月它变成了雾里的一团灰。'
             '护士说这是"实验需要"，给我加了一种滴眼液，滴下去火烧一样疼。'
             '他们说疼说明有效。我半夜偷偷留着一点药水，倒进了床头的水杯里'
             '——第二天水杯不见了，床单被换成了新的。他们什么都看得到，'
             '却假装看不见我在害怕。视力退潮的地方，声音开始涨潮：'
             '我能听见楼下洗碗的水流，听见三层楼外的争吵，'
             '听见我自己的眼球在眼窝里转动。医生，这真的正常吗？'
             '还有一件事：昨晚我梦见我看得见。梦里我在签一份文件，看得很清楚，'
             '签完抬头想笑，镜子里的我却没有眼睛。醒来的时候，枕头是湿的'
             '——是眼泪还是滴眼液，我分不出来。'},
    {'title': '病患日记 · 六｜我能听见你眨眼（阿彻）',
     'text': '今天的检测里，我说出了隔壁房间里硬币的正面。他们狂喜，'
             '在玻璃外面又写又画。可他们不知道代价。现在我闭上眼就能"看见"整个楼层'
             '——不是画面，是一张声音织成的网：水管的滴漏是网上的结，'
             '电路的嗡鸣是网线，还有一台仪器，每隔四秒跳一次，像心脏起搏器，'
             '从地下三层一直跳进我的枕头。我再也睡不着。白天的时候声音退一点，'
             '我就能睡着吗？不——白天有另一种声音，墙壁里有东西在爬，很轻，很快，'
             '可他们说他听不见。昨天 305 床对着墙说了一夜的话，今天他不见了。'
             '他的门牌还在，床铺已经冷了。'
             '医生今天给我加了药量。他说我在"过度联想"。'
             '可如果一切都是联想，为什么墙里的爬行声，在我吃药之后会停？'
             '药聋的到底是我的耳朵，还是我的判断力？'},
    {'title': '主管报告 · 七｜"静默穹顶"季度评估',
     'text': '「静默穹顶」季度评估。摘要：项目已进入不可逆收获期。'
             '前期投入（320 名各级受试者、两代致盲药剂、'
             '以及一位首席研究员的"自愿转化"）均已折旧完毕。当前资产：'
             '七名具备超常听觉定位能力的稳定受试体；其中 7 号个体的定位误差小于 0.3 米，'
             '且不再需要任何镇痛维持。展望：军事应用（声纹追踪、废墟搜救、敌后渗透）'
             '与民用康复（盲人回声训练）双轨授权已在洽谈。风险项：'
             '受试体情绪波动与"幻听合群"现象，即受试体声称能听见彼此。'
             '本主管认为，该现象恰恰证明：黑暗不是缺陷，是进化给我们留的一扇门。'
             '我们只需要把它推开。'
             '补充：董事会已批准在下一财年复制"静默穹顶"模式至另外三座设施。'
             '名称候选已确定。我们不再需要说服任何人——数据自己会说话，'
             '而说出来的每一个字，都值一座金库。'},
    {'title': '主管报告 · 八｜关于"消耗品"一词的使用规范',
     'text': '关于"消耗品"一词的使用规范。近期部分员工对内部通报中使用"消耗品"'
             '指代受试者表示不适。特此说明：一、所有受试者均签署知情同意，'
             '其法律身份为项目合作者，但从投入产出角度，'
             '与本项目中使用的 12000 只实验白鼠无本质差异。二、本项目为期十四年，'
             '累计产出可申请专利 87 项。每一项专利背后，按平均计算，'
             '需要 3.7 名受试者的完整感官作为"研发成本"。这是文明的定价。'
             '三、员工的同理心过剩将直接影响数据采集的客观性。即日起，'
             'B 区以下楼层实行轮岗制，单人连续驻留不得超过两周。'
             '四、停电事故与 7 号逃逸事件已淡化处理，无需再议。'
             '地下三层的通道已焊死。桌上那些档案，烧掉。'
             '附件一：焚化记录（已销毁）。附件二：B 区失踪员工名单（已销毁）。'
             '附件三：7 号在逃逸当晚带回地下室的一件物品照片'
             '——那是一枚儿童哨子。本主管拒绝解释，但保留它。'},
    {'title': '护工记录 · 九｜停电那晚',
     'text': '我在这里干了十一年，烧过尸体的头发，刷过手术台的血，'
             '我以为没有什么能让我再做噩梦。停电那晚我值夜班。整个 B 区的黑'
             '不是普通停电——应急灯闪了两下也灭了，是有人故意断了全部电源，'
             '包括地下三层的门禁。黑暗里我听见很多门同时被打开的声音，'
             '像一排琴键被按下去。然后是脚步声，赤脚的，很多，从楼下往上走，'
             '不快，也不慢，非常有秩序。我躲进清洁间，把门反锁。'
             '它们从我门前经过，不说话，只有呼吸——那么多人，呼吸却像一个声音。'
             '天亮之后，电梯里贴了封条，走廊重刷了漆，班表上那一夜被删掉了。'
             '我申请调岗，被拒绝。他们说：你什么都没看见。'
             '昨晚我又值了夜班。不是排班，是我自己想去的。'
             '我在 B 区的楼梯口放了一台录音机。如果有脚步声，我想留住它。'
             '早上回放：十二个小时，全是我的呼吸。中间有一段，'
             '我数不出自己的呼吸声——那一段里，我到底在哪儿？'},
    {'title': '护工记录 · 十｜地下三层的门',
     'text': '这是我的最后一份记录。焊接地下三层通道的那天我就在现场，'
             '焊枪的火星里，我听见门后有人在敲——不是乱敲，是三短，三长，三短，'
             '和 302 床那个孩子生前哼的调子一模一样。工头让我戴耳塞，'
             '说里面只是通风管道。可我知道通风管不会在敲完之后，'
             '把你的名字敲出来。它敲的是"伊——芙——琳"。那是那个瞎姑娘的名字。'
             '她不是实验体，她什么都没签过，她是被她哥哥的声音骗下来的。'
             '昨天开始，走廊的应急灯每天凌晨都会自己闪三下。灯灭的间隙里，'
             '我能听见天花板上有细细的爬行声，往电梯井的方向去了。'
             '如果有人读到这份记录：别去数墙上的刻痕。第七道之后，是倒着数的。'
             '写完这些我就把本子烧了。火光里我看见墙上有新的刻痕，'
             '不是我的粉笔，也不是那孩子的——更旧，更深，一层压着一层。'
             '原来早在我们所有人之前，这栋楼里就已经有人数过日子了。'
             '数到七，然后倒着数回去。'},
]

# ---------------- 随机词条（每次进关随机一个本局修正） ----------------
MODIFIERS = [
    {'key': 'nightmare', 'name': '噩梦缠身', 'desc': '怪物速度 +10%',
     'monster_speed': 1.10},
    {'key': 'crash',     'name': '系统崩溃', 'desc': '视野极度模糊（微光更弱、灰雾更浓）',
     'vision_blur': True},
    {'key': 'abyss',     'name': '寂静深渊', 'desc': '所有音效音量 -40%', 'quiet': True},
]

# ---------------- 运行期全局数据 ----------------
player_lives = START_LIVES
collected_fuses = 0
collected_diaries = 0        # 已收集日记数（死亡保留）
player = None
level_manager = None
current_level = 1            # 当前关卡编号
active_modifier = None       # 本局随机词条
settings_open = False        # 设置子面板（属于主菜单，不占状态机）
level_select_open = False    # 关卡选择子面板（属于主菜单）
archive_open = False         # 残存记忆档案库子面板（属于主菜单）
lore_read_open = False       # 档案库阅读子面板（占满屏幕长文本）
diary_open = False           # 正在阅读日记（全场冻结）
scare_active = False
scare_timer = 0.0
danger_k = 0.0
monster_step_timer = 0.0
buzz_timer = 0.0
fear_value = [0.0]           # ★ 恐怖值 0~100（规格三）
is_heartbeat_playing = False # ★ 心跳单例守卫（防叠加爆音）
_exhaust_pulse = [0.0]       # ★ 力竭红屏脉冲 0~1
_fear_scare_timer = [4.0]    # ★ 恐怖值>80 的急促惊悚音计时器
_scrape_timer = 0.0          # ★ 金属刮擦接近触发计时器
thunder_timer = 300.0        # ★ 规格五：雷暴倒计时（每 300 秒一次）
thunder_left = 0.0           # ★ 雷暴剩余时间（60 秒）
thunder_active = False       # ★ 雷暴进行中
thunder_los_timer = 0.0      # ★ 雷暴期 LOS 射线节流（0.5 秒/次）
THUNDER_INTERVAL = 300.0
THUNDER_DURATION = 60.0
ambient_event_timer = 8.0

WALLS = []
MONSTERS = []                # 聆听者（主怪）
SPIDERS = []                 # （旧版盲蛛丝线——已被白丝陷阱取代，类定义保留兼容）
WEBS = []                    # ★ 白丝陷阱（盲蛛重构：踩中减速不致死，可绕行）
SPIDER_LEGS = []             # ★ 盲蛛降临蛛腿（动画实体，关卡卸载统一销毁）
CROWS = []                   # 乌鸦（惊飞巨响）
SONARS = []                  # 伪声呐陷阱
DIARIES = []                 # 未收集的日记
CABINETS = []                # 柜子（可钻入躲避·透孔窥视）
PIPES = []                   # 可拾取的空管子
FUSES = []
STONES = []
ECHO_SPHERES = []
RIPPLES = []
ECHO_FADE = []               # ★ 回声登记队列（模式复位计时，8 秒）
ECHO_GHOSTS = []             # ★ 规格一：青色半透明幽灵方块（体积高亮，8 秒淡出）
RAMPS = []                   # ★ 可行走楼梯（解析斜坡，高度检测回退用）
PLATFORMS = []               # ★ 抬高平台（出生高台/出口高台，顶部可行走）
WALKABLES = []               # ★ 可行走表面注册表（地面/平台/地下室地板，解析判定用）
spawn_points = []            # ★ 多出生点列表（每关加载时填充，死亡安全重生用）
# ---- ★ 第三关「核心实验室」实体列表 ----
DOORS = []                   # 推拉门（静音开门 / 暴力撞门）
WARNING_LIGHTS = []          # 应急闪烁灯（怪物距离驱动）
BLOODPOOLS = []              # 血迹（踩上减速 + 黏腻脚步）
DRIP_PIPES = []              # ★ 滴水管道（回声可显形 + 3D 水滴声）
ELEC_BOXES = []              # ★ 配电箱/电线（回声可显形 + 3D 电流声）
MIRRORS = []                 # 破碎的镜子（回声扫过触发玻璃音）
TANKS = []                   # 玻璃培养罐（阻挡通行 + 沉闷回音）
TABLES = []                  # 手术台（搜查：50% 报告 / 30% 门禁卡 / 20% 空）
DRAWERS = []                 # 抽屉柜（搜查：45% 空 / 35% 恢复体力氧气 / 20% 惊吓噪音）
REPORTS = []                 # 残缺实验报告（白色发光四边形，贴地旋转）
KEYCARDS = []                # 红色门禁卡
MAIN_DOORS = []              # 主控门（携带门禁卡按 E 通关）
AMBIENT_SOUNDS3D = []        # ★ 房间 3D 环境音（隐藏实体：时钟滴答/水滴）
SFX_LOG = []                 # 音效播放日志（自动化测试与调试用）

# ---- ★ 随机 BGM 与随机惊吓环境音（本轮新增，规格）----
BGM_RANDOM_FILES = ['bgm_random_1.mp3', 'bgm_random_2.mp3',
                    'bgm_random_3.mp3']   # 随机 BGM 候选（assets/sounds/ 下）
SCARE_RANDOM_FILES = ['sfx_scare_whisper.mp3', 'sfx_scare_thunder.mp3',
                      'sfx_scare_scream.mp3', 'sfx_scare_metal.mp3']  # 随机惊吓候选
SCARE_AMBIENCE_INTERVAL = (15.0, 45.0)   # 惊吓音随机触发间隔区间（秒，规格）
scare_ambience_timer = random.uniform(15.0, 45.0)   # 惊吓音计时器（仅 PLAYING 计时）
scare_audio_pool = []                    # 已创建的惊吓音 Audio（生命周期管理）

# =====================================================================================
#  ★ 大故事库（STORY_DB，规格三.2）——12 条日记 + 6 条实验报告。
#    主题：盲女伊芙琳 / 静默穹顶实验 / 致盲药剂 / 变异病友 / 哥哥埃利奥特（7 号）。
#    各关文本实体从库中按洗牌袋取用（同型不重复直至耗尽），绝不空文本。
# =====================================================================================
# ---------------- 局内碎片池（规格一.2：50 条互不重复的环境叙事，10~30 字）----------------
FRAGMENT_POOL = [
    '「便签 · 血迹旁」护士把镇定剂换成了盐水。我们都会死在这里。',
    '「涂鸦 · 墙角」第七道刻痕之后，他们开始倒着数。',
    '「药袋 · 撕口」滴眼液 ZK-7：疼痛说明有效。',
    '「纸条 · 枕下」305 的床铺是冷的，门牌还亮着。',
    '「磁带标签」儿童笑声，来源不明，7 号反复播放。',
    '「塞在门缝的纸」别数走廊的门。数到第十扇，回头。',
    '「培养罐手印」罐壁上的手掌，比我哥哥的小一号。',
    '「值班表 · 焦痕」B 区以下，单人驻留不得超过两周。',
    '「病历 · 撕页」视觉皮层：已切除。听觉皮层：未测量。',
    '「电报式字条」三短。三长。三短。别回敲。',
    '「粉笔字 · 电梯井」爬行声往井里去了。别开电梯。',
    '「日记最后一页」我下去找他。如果我错了，请烧掉档案室。',
    '「报告残页」致盲药剂 ZK-7：全盲率 100%。',
    '「检测记录」听觉阈值 40000Hz，耳膜穿孔仍能听到脚步。',
    '「收容日志」7 号拒绝进食第 9 天，自行拆卸约束装置。',
    '「停电通告」B 区失压 47 分钟。原因：人为。',
    '「处置单」地下三层通道：焊接封闭，永久。',
    '「评估尾页」它们不恨我们。它们只是在等。',
    '「停尸房抽屉」第 13 号抽屉是从里面锁上的。',
    '「监控室排班」夜班已取消。没有人说明原因。',
    '「手术台铭牌」本台累计使用：1194 次。',
    '「药柜标签」镇静剂库存：零。请勿再申请。',
    '「墙纸下压着」他们说黑暗会习惯。骗人。',
    '「通风口铁丝」有一撮头发卡在这里。很新。',
    '「签收单」新增受试体 7 名。名单口头传达。',
    '「体温记录」302 号连续三夜体温 39 度。拒医。',
    '「电梯检验贴」停用。故障：自行移动至 B3。',
    '「锅炉房告示」热水中断。管道里有异物。',
    '「挂号信」妈妈：我签约了。别来找我。',
    '「头顶广播」今晚九点后，请勿回应任何敲门声。',
    '「墙角刻字」我听得见。你们装听不见。',
    '「碎玻璃上」血从 B3 一直滴到了电梯口。',
    '「餐盘底面」别吃周四的肉。求你。',
    '「淋浴间门」花洒在漏水。滴的节奏不对。',
    '「点名册」305 与 306 两行，被同一支笔划掉。',
    '「病历夹」患者的耳朵在继续长大。停不下来。',
    '「鼠笼空了」B3 的老鼠全死了。同一天夜里。',
    '「白板残字」第 7 号不是失败——是超额完成。',
    '「窗帘后」窗外没有城市灯火。从来都没有。',
    '「缝在枕套里」如果我没醒，别叫醒我。',
    '「走廊指示牌」B2 方向的箭头被指甲划烂了。',
    '「药瓶背面」过量会导致"听觉过敏"。慎用。',
    '「手套箱里」第 44 副手套，指尖全磨破了。',
    '「消防栓封条」上一次开启：停电那晚。',
    '「打卡机纸条」凌晨 3:33 全员打卡。无人记得。',
    '「座椅背面」别坐窗边。它会记住你的轮廓。',
    '「病历附录」他一直说：墙里有人学我说话。',
    '「锅炉压力表」指针在无人时段反复打满。',
    '「信封残角」收件人被撕掉了。只剩：速逃。',
    '「地面拖痕」几十双拖鞋的印子，全部朝着井口。',
]

# ---------------- 碎片持久化（规格一.3：save_data.json）----------------
FRAG_SAVE_PATH = os.path.join(SCRIPT_DIR, 'save_data.json')
collected_fragment_ids = []      # ★ 已收集碎片的 ID 列表（跨局持久化）
_round_used_ids = set()          # 本局已分配出去的碎片 ID（防同局重复）
current_round_fragments = 0      # ★ 单局已拾取碎片数（上限 8）
dev_all_unlocked = False         # ★ 开发者模式：全剧情解锁标记（持久化到 save_data.json）


def load_fragment_data():
    """★ 规格一.3：启动时读取 save_data.json；文件不存在则创建空档"""
    global collected_fragment_ids
    try:
        if os.path.exists(FRAG_SAVE_PATH):
            with open(FRAG_SAVE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ids = data.get('collected_fragment_ids', [])
            collected_fragment_ids = [int(i) for i in ids
                                      if 0 <= int(i) < len(FRAGMENT_POOL)]
            global dev_all_unlocked
            dev_all_unlocked = bool(data.get('dev_unlock_all', False))
        else:
            save_fragment_data()            # 首次运行：创建存档文件
    except Exception as e:
        print(f'（碎片存档读取失败：{e}）')


def save_fragment_data():
    try:
        with open(FRAG_SAVE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'collected_fragment_ids': collected_fragment_ids,
                       'dev_unlock_all': dev_all_unlocked}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'（碎片存档写入失败：{e}）')


def next_fragment():
    """★ 规格二.2：从池中剔除已收集 ID 后随机抽一个（同局不重复）。
    返回 (碎片ID, 文本)。池耗尽时允许复用本局未用过的 ID。"""
    avail = [i for i in range(len(FRAGMENT_POOL))
             if i not in collected_fragment_ids and i not in _round_used_ids]
    if not avail:
        avail = [i for i in range(len(FRAGMENT_POOL))
                 if i not in _round_used_ids]
    if not avail:
        avail = list(range(len(FRAGMENT_POOL)))
    fid = random.choice(avail)
    _round_used_ids.add(fid)
    # ★ 规格四.2：空文本容错——绝不让 UI 收到空字符串
    frag = FRAGMENT_POOL[fid]
    return fid, (frag if frag else '这段记录已经被血迹模糊，无法辨认……')

# 死亡嘲讽（英文男声台词，占位语音 taunt_1..4 + 屏幕字幕）
TAUNTS = [
    'Pathetic mouse.',
    'Your screams are so clear.',
    'I can smell your fear, Evelyn.',
    'The dark belongs to me.',
]

# =====================================================================================
#  二、音效系统：★ 全部音频文件统一放在 assets/sounds/ 文件夹中（标准化目录规格）。
#    查找顺序（全部位于 assets/sounds/ 内）：① 规格资源名 → ② 代码合成/下载的 wav →
#    ③ 网络下载的 mp3。所有 Audio() 调用严格包裹 try-except：文件不存在或加载
#    失败时 print("警告：未找到音频文件 xxx") 并继续运行，绝不闪退。
# =====================================================================================
RESOURCE_FILES = {   # 规格资源名（同样位于 assets/sounds/ 文件夹内）
    'bgm':       'bgm_horror.mp3',
    'wind':      'wind_ambient.mp3',
    'roar':      'monster_scream.mp3',
    'heartbeat': 'heartbeat.wav',
    'jumpscare': 'jumpscare.mp3',
    'step':      'step_walk.wav',
    'taunt1':    'taunt_1.wav',
    'taunt2':    'taunt_2.wav',
    'taunt3':    'taunt_3.wav',
    'taunt4':    'taunt_4.wav',
    # ---- ★ 本轮新增的 5 个环境/交互音效（用户自备 mp3，位于 assets/sounds/）----
    'door_open':    'sfx_door_open.mp3',         # 开门声
    'door_close':   'sfx_door_close.mp3',        # 关门声
    'clock_tick':   'sfx_clock_tick.mp3',        # 时钟滴答（监控室 3D 循环）
    'thunderstorm': 'ambient_thunderstorm.mp3',  # 雷雨环境（全局循环）
    'water_drip':   'sfx_water_drip.mp3',        # 水滴声（停尸房/管道 3D 循环）
    'fuse_hum':     'sfx_fuse_hum.wav',          # 电流嗡鸣（保险丝/应急灯 3D 循环）
    'elec_hum':     'sfx_electricity_hum.wav',   # 配电箱电流声（缺失走 fuse_hum 合成）
    'metal_scrape': 'sfx_metal_scrape.mp3',      # 金属刮擦（靠近罐/抽屉随机触发）
    'monster_scream': 'sfx_monster_scream.mp3',  # ★ 规格四.1：怪物发现玩家尖叫
    'thunder_burst': 'sfx_scare_thunder.mp3',   # ★ 规格五：雷暴炸雷
}

SOUND_FILES = {
    'bgm':          'bgm.wav',
    'wind':         'wind.wav',
    'breath':       'breath.wav',
    'drip':         'drip.wav',
    'clang':        'clang.wav',
    'buzz':         'buzz.wav',
    'step':         'step.wav',
    'step_run':     'step_run.wav',
    'sonar':        'sonar.wav',
    'heartbeat':    'heartbeat.wav',
    'monster_step': 'monster_step.wav',
    'mbreath':      'mbreath.wav',
    'roar':         'roar.wav',
    'skill':        'skill.wav',
    'gasp':         'gasp.wav',
    'flap':         'flap.wav',
    'pipe_land':    'pipe_land.wav',
    'jumpscare':    'jumpscare.wav',
    'taunt1':       'taunt1.wav',
    'taunt2':       'taunt2.wav',
    'taunt3':       'taunt3.wav',
    'taunt4':       'taunt4.wav',
    'web_tear':     'web_tear.wav',     # ★ 白丝撕裂声（盲蛛重构，合成兜底）
    'spider_hiss':  'spider_hiss.wav',  # ★ 盲蛛嘶嘶声（合成兜底）
    'fuse_hum':     'fuse_hum.wav',     # ★ 电流嗡鸣合成兜底（3D 循环）
    'elec_hum':     'fuse_hum.wav',     # ★ 配电箱共用电流合成兜底
    'metal_scrape': 'metal_scrape.wav', # ★ 金属刮擦合成兜底
    'monster_scream': 'roar.wav',       # ★ 怪物尖叫合成兜底（复用嘶吼）
    'thunder_burst': 'thunderstorm.wav', # ★ 雷暴合成兜底（复用雷雨）
    'door_creak':   'door_creak.wav',   # ★ 静音开门的微小吱呀声（door_open 的合成兜底）
    'door_close':   'door_close.wav',   # ★ 关门声的合成兜底
    'clock_tick':   'clock_tick.wav',   # ★ 时钟滴答的合成兜底（监控室 3D 循环）
    'thunderstorm': 'thunderstorm.wav', # ★ 雷雨环境的合成兜底（全局循环）
    'water_drip':   'water_drip_loop.wav',  # ★ 水滴声的合成兜底（停尸房 3D 循环）
    'door_bang':    'door_bang.wav',    # ★ 暴力撞门的巨大砰声
    'glass':        'glass.wav',        # ★ 镜子被回声扫过的高频玻璃音
    'tank_echo':    'tank_echo.wav',    # ★ 培养罐反弹的沉闷回音
    'squish':       'squish.wav',       # ★ 血迹上的黏腻脚步声
}

SOUND_URLS = {
    'bgm':       'https://assets.mixkit.co/active_storage/sfx/2434/2434-preview.mp3',
    'wind':      'https://assets.mixkit.co/active_storage/sfx/2382/2382-preview.mp3',
    'step':      'https://assets.mixkit.co/active_storage/sfx/2167/2167-preview.mp3',
    'roar':      'https://assets.mixkit.co/active_storage/sfx/2975/2975-preview.mp3',
    'heartbeat': 'https://assets.mixkit.co/active_storage/sfx/2076/2076-preview.mp3',
    'jumpscare': 'https://assets.mixkit.co/active_storage/sfx/2975/2975-preview.mp3',
}


def _audio_candidates(name):
    """★ 音频查找顺序（规格：所有音频都在 assets/sounds/ 文件夹中）：
    ① assets/sounds/<规格资源名>（如 assets/sounds/bgm_horror.mp3）
    ② assets/sounds/<代码合成或下载的 wav 名>
    ③ assets/sounds/<name>.mp3（网络下载的 mp3）
    等价于把所有 Audio('xxx') 都改为 Audio('assets/sounds/xxx')。
    ★ 未知音效名不产生空路径（防止把 assets/sounds 目录本身当作音频文件）。"""
    out = []
    # ★ 嘲讽音效规格命名 voice_taunt_N.mp3 优先——玩家放入即被 .play() 触发
    if name.startswith('taunt') and name[-1].isdigit():
        out.append(os.path.join(SOUND_DIR, f'voice_taunt_{name[-1]}.mp3'))
    res = RESOURCE_FILES.get(name)
    if res:
        out.append(os.path.join(SOUND_DIR, res))       # ★ sounds/规格资源
    local_name = SOUND_FILES.get(name, '')
    if local_name:                                     # ★ 仅登记真实存在的文件名
        out.append(os.path.join(SOUND_DIR, local_name))
    out.append(os.path.join(SOUND_DIR, name + '.mp3'))  # ★ sounds/下载 mp3
    return out


def try_download_sounds():
    """尝试用 urllib.request 从网络直链下载音效到 assets/sounds/（5 秒超时、RIFF 头校验），
    失败静默跳过——代码合成兜底，绝不闪退。"""
    try:
        os.makedirs(SOUND_DIR, exist_ok=True)
    except Exception:
        return
    for name, url in SOUND_URLS.items():
        dest = os.path.join(SOUND_DIR, SOUND_FILES[name])
        if os.path.exists(dest) or os.path.exists(os.path.join(SOUND_DIR, name + '.mp3')):
            continue
        tmp = dest + '.tmp'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp, open(tmp, 'wb') as f:
                f.write(resp.read(2 * 1024 * 1024))
            if os.path.getsize(tmp) > 20 * 1024:
                with open(tmp, 'rb') as hf:
                    head = hf.read(4)
                if head == b'RIFF':
                    os.replace(tmp, dest)
                else:
                    os.replace(tmp, os.path.join(SOUND_DIR, name + '.mp3'))
            else:
                os.remove(tmp)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass


_WAV_RATE = 22050


def _write_wav(path, sample_func, duration, volume=1.0):
    """把采样函数合成为 16bit 单声道 wav（纯代码生成，无外部素材）"""
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
    """首次运行代码合成全部缺失音效；任何失败只影响该条（回退 print 占位）。"""
    try:
        os.makedirs(SOUND_DIR, exist_ok=True)
        specs = {}

        def _bgm(t, dt):      # 恐怖 BGM：拍频低频轰鸣 + 次声 + 诡异颤音（6s 无缝循环）
            s = (0.5 * math.sin(2 * math.pi * 40 * t)
                 + 0.45 * math.sin(2 * math.pi * 41.5 * t)
                 + 0.3 * math.sin(2 * math.pi * 30 * t)
                 + 0.22 * math.sin(2 * math.pi * 61 * t)
                 + 0.05 * math.sin(2 * math.pi * 662 * t)
                 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 2.0)))
            return math.tanh(s * 1.5) * 0.5

        specs['bgm.wav'] = (_bgm, 6.0, 0.45)

        wind_lp = [0.0]

        def _wind(t, dt):     # 持续风声：低通噪声 + 慢速起伏（4s 无缝循环）
            wind_lp[0] += 0.08 * ((random.random() * 2 - 1) - wind_lp[0])
            return wind_lp[0] * (0.55 + 0.45 * math.sin(2 * math.pi * t / 4.0)) * 1.2

        specs['wind.wav'] = (_wind, 4.0, 0.50)

        breath_lp = [0.0]

        def _breath(t, dt):   # 玩家呼吸（4s 一个循环；屏息时循环音量归零）
            breath_lp[0] += 0.2 * ((random.random() * 2 - 1) - breath_lp[0])
            if t < 1.7:
                env = (t / 1.7) ** 1.5 * 0.8
            else:
                env = max(0.0, 1.0 - (t - 1.7) / 2.3) ** 1.5 * 0.6
            return breath_lp[0] * env * 1.4

        specs['breath.wav'] = (_breath, 4.0, 0.55)

        def _drip(t, dt):     # 滴水：950→600Hz 水滴 + 轻微回声
            s = math.sin(2 * math.pi * (950 - 350 * min(t * 12, 1)) * t) \
                * math.exp(-t * 55)
            if 0.10 <= t < 0.16:
                s += 0.4 * math.sin(2 * math.pi * 900 * (t - 0.10)) \
                    * math.exp(-(t - 0.10) * 55)
            return s

        specs['drip.wav'] = (_drip, 0.22, 0.5)

        def _clang(t, dt):    # 远处金属碰撞：非谐和泛音长余音
            s = (0.5 * math.sin(2 * math.pi * 523 * t)
                 + 0.35 * math.sin(2 * math.pi * 1337 * t)
                 + 0.25 * math.sin(2 * math.pi * 2117 * t)
                 + 0.2 * (random.random() * 2 - 1) * math.exp(-t * 90))
            return s * math.exp(-t * 7)

        specs['clang.wav'] = (_clang, 0.7, 0.35)

        tear_lp = [0.0]

        def _web_tear(t, dt):     # ★ 白丝撕裂：高频噪声颤裂 + 快速衰减（0.5s）
            raw = random.random() * 2 - 1
            tear_lp[0] += 0.5 * (raw - tear_lp[0])
            flutter = 0.6 + 0.4 * math.sin(2 * math.pi * 38 * t)
            return (tear_lp[0] * 1.8 + 0.25 * math.sin(2 * math.pi * 1900 * t)) \
                * flutter * math.exp(-t * 6.5)

        hiss_lp = [0.0]

        def _spider_hiss(t, dt):  # ★ 盲蛛嘶嘶：低通噪声 + 100Hz 体腔共振，中段最响
            raw = random.random() * 2 - 1
            hiss_lp[0] += 0.12 * (raw - hiss_lp[0])
            env = math.sin(math.pi * min(t / 0.9, 1.0)) ** 0.7
            return (hiss_lp[0] * 2.2 + 0.3 * math.sin(2 * math.pi * 100 * t)) * env

        specs['web_tear.wav'] = (_web_tear, 0.5, 0.55)
        specs['spider_hiss.wav'] = (_spider_hiss, 0.9, 0.55)

        def _fuse_hum(t, dt):     # ★ 电流嗡鸣：工频哼声 + 高频滋（3s 无缝循环）
            s = (0.5 * math.sin(2 * math.pi * 100 * t)
                 + 0.35 * math.sin(2 * math.pi * 120 * t)
                 + 0.18 * math.sin(2 * math.pi * 240 * t)
                 + 0.06 * (random.random() * 2 - 1))
            return math.tanh(s * 1.6) * 0.42

        specs['fuse_hum.wav'] = (_fuse_hum, 3.0, 0.4)

        scrape_lp = [0.0]

        def _metal_scrape(t, dt):  # ★ 金属刮擦：带阻噪声缓慢衰减（0.45s）
            raw = random.random() * 2 - 1
            scrape_lp[0] += 0.3 * (raw - scrape_lp[0])
            return (scrape_lp[0] * 1.6 + 0.2 * math.sin(2 * math.pi * 1600 * t)) \
                * math.exp(-t * 7)

        specs['metal_scrape.wav'] = (_metal_scrape, 0.45, 0.4)

        def _buzz(t, dt):     # 保险丝电流滋滋声
            gate = 1.0 if math.sin(2 * math.pi * 47 * t) >= 0 else 0.2
            return (random.random() * 2 - 1) * gate * math.exp(-t * 14)

        specs['buzz.wav'] = (_buzz, 0.18, 0.4)

        specs['step.wav'] = (  # 行走脚步
            lambda t, dt: (0.6 * math.sin(2 * math.pi * 95 * t)
                           + 0.5 * (random.random() * 2 - 1)) * math.exp(-t * 45),
            0.09, 0.55)

        specs['step_run.wav'] = (  # 奔跑重踏
            lambda t, dt: (0.9 * math.sin(2 * math.pi * 70 * t)
                           + 0.6 * (random.random() * 2 - 1)) * math.exp(-t * 28),
            0.13, 0.80)

        sonar_phase = [0.0]

        def _sonar(t, dt):    # 声呐敲击：1200→450Hz 扫频
            f = 1200.0 - 750.0 * (t / 0.6)
            sonar_phase[0] += 2 * math.pi * f * dt
            return math.sin(sonar_phase[0]) * math.exp(-t * 3.5)

        specs['sonar.wav'] = (_sonar, 0.6, 0.60)

        def _heartbeat(t, dt):  # 心跳：两记 52Hz 闷响（pitch 动态调速）
            s = 0.0
            for t0, amp in ((0.05, 1.0), (0.32, 0.72)):
                u = t - t0
                if 0.0 <= u < 0.22:
                    s += math.sin(2 * math.pi * 52 * u) * math.exp(-u * 16) * amp
            return s

        specs['heartbeat.wav'] = (_heartbeat, 0.7, 0.85)

        specs['monster_step.wav'] = (  # 聆听者沉重脚步
            lambda t, dt: (0.9 * math.sin(2 * math.pi * 42 * t)
                           + 0.35 * (random.random() * 2 - 1)) * math.exp(-t * 16),
            0.16, 0.80)

        mbreath_lp = [0.0]

        def _mbreath(t, dt):  # 聆听者沉重喘息（3D 音效挂载点）
            mbreath_lp[0] += 0.12 * ((random.random() * 2 - 1) - mbreath_lp[0])
            env = min(t * 8, 1.0) * max(0.0, 1.0 - (t - 0.35) / 0.45)
            return (mbreath_lp[0] * 0.8
                    + 0.5 * math.sin(2 * math.pi * 55 * t)) * env

        specs['mbreath.wav'] = (_mbreath, 0.8, 0.6)

        def _roar(t, dt):     # 追击嘶吼：下坠锯齿 + 怒颤 + 尖啸，失真压缩
            f = 300.0 - 210.0 * (t / 0.9)
            saw = 2.0 * ((f * t) % 1.0) - 1.0
            trem = 0.6 + 0.4 * math.sin(2 * math.pi * 16 * t)
            squeal = 0.3 * math.sin(2 * math.pi * 1200 * (1.0 - t * 0.8) * t)
            s = 0.55 * saw + 0.4 * (random.random() * 2 - 1) * trem + squeal
            env = min(t * 25, 1.0) * math.exp(-t * 2.2)
            return math.tanh(s * 2.5) * env

        specs['roar.wav'] = (_roar, 0.9, 0.9)

        def _skill(t, dt):    # 技能音：双音上行风铃
            if t < 0.15:
                return math.sin(2 * math.pi * 660 * t) * math.exp(-t * 18)
            u = t - 0.15
            return 0.8 * math.sin(2 * math.pi * 990 * u) * math.exp(-u * 14)

        specs['skill.wav'] = (_skill, 0.35, 0.55)

        def _gasp(t, dt):     # 屏息耗尽的强制喘息：急促吸气噪声
            env = min(t * 20, 1.0) * max(0.0, 1.0 - (t - 0.25) / 0.25)
            return (random.random() * 2 - 1) * env * math.sin(math.pi * min(t * 2.5, 1))

        specs['gasp.wav'] = (_gasp, 0.5, 0.8)

        flap_lp = [0.0]

        def _flap(t, dt):     # 乌鸦扑腾：快速拍打（22Hz 门控噪声）
            flap_lp[0] += 0.3 * ((random.random() * 2 - 1) - flap_lp[0])
            gate = 1.0 if math.sin(2 * math.pi * 11 * t) >= 0 else 0.15
            return flap_lp[0] * gate * 1.5

        specs['flap.wav'] = (_flap, 0.9, 0.8)

        def _pipe_land(t, dt):  # 管子落地：金属管滚落的哐当余音
            s = (0.7 * math.sin(2 * math.pi * 710 * t)
                 + 0.5 * math.sin(2 * math.pi * 1890 * t)
                 + 0.3 * (random.random() * 2 - 1)) * math.exp(-t * 9)
            return s

        specs['pipe_land.wav'] = (_pipe_land, 0.7, 0.7)

        def _jumpscare(t, dt):  # 突脸尖叫
            vib = 1.0 + 0.06 * math.sin(2 * math.pi * 11 * t)
            square = 1.0 if math.sin(2 * math.pi * 1900 * vib * t) >= 0 else -1.0
            f = 2800.0 - 2300.0 * (t / 1.3)
            noise = random.random() * 2 - 1
            env = min(t * 30.0, 1.0) * math.exp(-t * 0.8)
            sc = 0.45 * math.sin(2 * math.pi * f * t * 0.5)
            return (0.55 * square + sc + 0.35 * noise) * env

        specs['jumpscare.wav'] = (_jumpscare, 1.3, 0.95)

        # 死亡嘲讽占位语音 ×4：低沉"男声"质感的合成哼语（不同音高/节奏），
        # 真实台词以英文字幕形式显示在屏幕上
        for idx, (pitch, rhythm) in enumerate(((105.0, 3.0), (97.0, 2.2),
                                               (112.0, 3.4), (90.0, 2.6)), start=1):

            def _taunt(t, dt, p=pitch, r=rhythm):
                saw = 2.0 * ((p * t) % 1.0) - 1.0
                soft = math.tanh(saw * 1.6)
                syll = 0.45 + 0.55 * abs(math.sin(2 * math.pi * r * t))
                env = min(t * 12, 1.0) * max(0.0, 1.0 - (t - 0.75) / 0.35)
                return soft * syll * env * 0.7

            specs[f'taunt{idx}.wav'] = (_taunt, 1.1, 0.6)

        # ===== ★ 第三关专属音效 =====

        # 门轨吱呀：缓慢的锯齿滑音（静音开门的"微小吱呀声"）
        creak_phase = [0.0]

        def _door_creak(t, dt):
            f = 180.0 + 60.0 * math.sin(2 * math.pi * 2.2 * t)
            creak_phase[0] += 2 * math.pi * f * dt
            saw = 2.0 * ((creak_phase[0] / (2 * math.pi)) % 1.0) - 1.0
            return math.tanh(saw * 1.2) * min(t * 8, 1.0) * math.exp(-t * 1.8)

        specs['door_creak.wav'] = (_door_creak, 1.4, 0.30)

        # 撞门砰声：55Hz 重击 + 噪声爆发（巨大的"砰"）
        def _door_bang(t, dt):
            s = (0.95 * math.sin(2 * math.pi * 55 * t)
                 + 0.8 * (random.random() * 2 - 1) * math.exp(-t * 30))
            return s * math.exp(-t * 9)

        specs['door_bang.wav'] = (_door_bang, 0.5, 0.95)

        # 高频玻璃音：2100/3400/4700Hz 非谐和簇 + 快速衰减（破碎的镜子）
        def _glass(t, dt):
            s = (0.4 * math.sin(2 * math.pi * 2100 * t)
                 + 0.3 * math.sin(2 * math.pi * 3400 * t)
                 + 0.25 * math.sin(2 * math.pi * 4700 * t)
                 + 0.25 * (random.random() * 2 - 1))
            return s * math.exp(-t * 12)

        specs['glass.wav'] = (_glass, 0.5, 0.45)

        # 沉闷回音：120Hz 单频 + 慢衰减（玻璃培养罐反弹）
        def _tank_echo(t, dt):
            return (math.sin(2 * math.pi * 120 * t)
                    * math.exp(-t * 5) * 0.9)

        specs['tank_echo.wav'] = (_tank_echo, 0.7, 0.5)

        # 黏腻脚步：低通噪声 + 湿润的"吧嗒"包络
        squish_lp = [0.0]

        def _squish(t, dt):
            squish_lp[0] += 0.25 * ((random.random() * 2 - 1) - squish_lp[0])
            env = min(t * 25, 1.0) * math.exp(-t * 22)
            return (squish_lp[0] * 1.3
                    + 0.3 * math.sin(2 * math.pi * 140 * t) * math.exp(-t * 25)) * env

        specs['squish.wav'] = (_squish, 0.14, 0.6)

        # ===== ★ 本轮新增音效的合成兜底（用户 mp3 缺失时自动启用）=====

        # 关门声：短促的滑轨"咔哒" + 低频落位闷响
        def _door_close(t, dt):
            if t < 0.25:                       # 滑轨摩擦（下滑锯齿）
                f = 260.0 - 340.0 * (t / 0.25)
                saw = 2.0 * ((f * t) % 1.0) - 1.0
                return math.tanh(saw * 1.3) * 0.5
            u = t - 0.25                        # 落位闷响
            if 0.0 <= u < 0.2:
                return (0.8 * math.sin(2 * math.pi * 80 * u)
                        + 0.4 * (random.random() * 2 - 1)) * math.exp(-u * 22)
            return 0.0

        specs['door_close.wav'] = (_door_close, 0.5, 0.55)

        # 时钟滴答：1 秒无缝循环——高音"滴"(0s) + 低音"答"(0.5s)
        def _clock_tick(t, dt):
            s = 0.0
            for t0, f, amp in ((0.02, 2100.0, 1.0), (0.52, 1500.0, 0.8)):
                u = t - t0
                if 0.0 <= u < 0.05:
                    s += (math.sin(2 * math.pi * f * u)
                          + 0.4 * (random.random() * 2 - 1)) * math.exp(-u * 130) * amp
            return s * 0.7

        specs['clock_tick.wav'] = (_clock_tick, 1.0, 0.55)

        # 雷雨环境：雨声（低通噪声底）+ 两记远处闷雷（40Hz 起伏），6 秒无缝循环
        rain_lp = [0.0]

        def _thunderstorm(t, dt):
            rain_lp[0] += 0.06 * ((random.random() * 2 - 1) - rain_lp[0])
            rain = rain_lp[0] * 1.1
            rumble = 0.0
            for t0, dur in ((2.2, 1.6), (4.9, 1.1)):
                u = t - t0
                if 0.0 <= u < dur:
                    swell = math.sin(math.pi * u / dur)
                    rumble += (math.sin(2 * math.pi * 38 * u)
                               + 0.3 * (random.random() * 2 - 1)) * swell * 0.5
            return rain + rumble

        specs['thunderstorm.wav'] = (_thunderstorm, 6.0, 0.5)

        # 水滴循环：3 秒内两滴错落的水滴（950→600Hz 下滑），其余留白
        drip_phase = [0.0]

        def _water_drip_loop(t, dt):
            s = 0.0
            for t0, f0 in ((0.5, 950.0), (2.1, 720.0)):
                u = t - t0
                if 0.0 <= u < 0.14:
                    s += math.sin(2 * math.pi * (f0 - 350 * min(u * 12, 1)) * u) \
                        * math.exp(-u * 42)
            return s

        specs['water_drip_loop.wav'] = (_water_drip_loop, 3.0, 0.5)

        for filename, (func, dur, vol) in specs.items():
            path = os.path.join(SOUND_DIR, filename)
            if not os.path.exists(path):
                _write_wav(path, func, dur, vol)
        return True
    except Exception as e:
        print(f'（音效合成失败，将使用文字音效占位：{e}）')
        return False


def load_audio(name, loop=False, volume=1.0):
    """普通音效加载（★ 全部路径位于 assets/sounds/，Audio 调用严格 try-except）：
    依次尝试候选文件（必须为真实存在的"文件"）→ 全部失败时
    print("提示：未找到音效文件 ...，游戏将静音运行。") 并返回 None
    （播放侧自动退化为文字音效，游戏继续运行，绝不闪退）。"""
    cands = _audio_candidates(name)
    for path in cands:
        if path and os.path.isfile(path):     # ★ os.path.exists 强校验（规格）
            try:
                aud = Audio(path, loop=loop, volume=volume, autoplay=False)
                print(f'✅ 音频加载成功: {os.path.basename(path)}')
                return aud
            except Exception:
                continue                     # 加载失败 → 尝试下一个候选
    primary = cands[0] if cands else os.path.join(SOUND_DIR, name)
    print(f'\033[91m❌ 严重警告: 未找到音频 {primary}——已降级为静音/文字占位，游戏继续运行\033[0m')
    return None


def load_3d_audio(name, loop=False, volume=1.0):
    """★ 3D 环绕音效（规格要求）：尝试 Audio(..., is_3d=True)。
    当前 Ursina 版本不支持该参数或加载失败时，退化为普通 Audio
    （由每帧的距离音量模拟听声辨位）。全部路径位于 assets/sounds/，
    Audio 调用严格 try-except：全部失败时 print 提示/警告并返回 None，绝不闪退。"""
    cands = _audio_candidates(name)
    for path in cands:
        if path and os.path.isfile(path):     # ★ os.path.exists 强校验（规格）
            try:
                aud = Audio(path, loop=loop, volume=volume,
                            autoplay=False, is_3d=True)      # 规格写法
                print(f'✅ 音频加载成功: {os.path.basename(path)}（3D 环绕）')
                return aud
            except TypeError:
                try:                                          # 老版本：无 is_3d 参数
                    aud = Audio(path, loop=loop, volume=volume, autoplay=False)
                    print(f'✅ 音频加载成功: {os.path.basename(path)}（普通模式）')
                    return aud
                except Exception:
                    return None
            except Exception:
                continue
    primary = cands[0] if cands else os.path.join(SOUND_DIR, name)
    print(f'\033[91m❌ 严重警告: 未找到音频 {primary}——已降级为静音，距离音量逻辑接管\033[0m')
    return None


def set_audio_position(audio, pos):
    """★ 每帧更新 3D 音效位置（规格：audio.position = monster.position）。
    依次尝试 ursina 的 position 属性与 Panda 原生 set3dAttributes；
    均不支持时静默失败——音量由距离逻辑接管。"""
    if audio is None:
        return
    try:
        audio.position = pos
        return
    except Exception:
        pass
    try:
        audio.clip.set_3d_attributes(pos.x, pos.y, pos.z, 0, 0, 0)
    except Exception:
        pass


print('============================================================')
print('  ★ 三重自检 · 音频资源审计（assets/sounds/，✅=命中 ❌=降级静音）')
print('============================================================')
try_download_sounds()
ensure_sound_assets()

# 常驻循环音
bgm_audio = load_audio('bgm', loop=True, volume=0.32)
_synth_bgm_backup = bgm_audio    # 内置合成 BGM（随机 BGM 文件缺失时的回退）
wind_audio = load_audio('wind', loop=True, volume=0.30)
breath_audio = load_audio('breath', loop=True, volume=0.35)
heartbeat_audio = load_audio('heartbeat', loop=True, volume=0.0)
thunderstorm_audio = load_audio('thunderstorm', loop=True, volume=0.30)  # ★ 雷雨环境音
_one_shot_cache = {}

SOUND_TEXT = {
    'bgm': '【BGM】嗡————（低沉不和谐的轰鸣萦绕）', 'wind': '【环境】呼——风声掠过',
    'breath': '（呼吸……呼吸……）', 'drip': '（嗒……水滴坠落）',
    'clang': '（哐————远处金属哀鸣）', 'buzz': '（滋……滋……电流微响）',
    'step': '（嗒……）', 'step_run': '（咚！咚！——狂奔炸响）',
    'sonar': '【回声】滴————（声呐扩散）', 'heartbeat': '（咚、咚……心跳）',
    'monster_step': '（咚——咚——沉重脚步）', 'mbreath': '【怪物】呼——嘶——',
    'roar': '【怪物嘶吼】呃 啊 啊 啊——！！！', 'skill': '【技能】嗡——',
    'gasp': '【喘息】哈啊——！！（巨大喘息声）', 'flap': '【乌鸦】扑棱棱——！！！',
    'pipe_land': '【管子】哐啷啷——（金属管滚落）', 'jumpscare': '【尖叫】呃啊啊啊——！',
    'taunt1': '【聆听者】Pathetic mouse.', 'taunt2': '【聆听者】Your screams are so clear.',
    'taunt3': '【聆听者】I can smell your fear, Evelyn.',
    'taunt4': '【聆听者】The dark belongs to me.',
    'door_creak': '（吱呀……门轨滑动的轻响）',
    'door_bang': '【巨响】砰！！——门被狠狠撞开，回音炸裂！',
    'glass': '（叮——高频的玻璃碎响）',
    'tank_echo': '（咚……培养罐反弹出沉闷的回音）',
    'squish': '（吧嗒……黏腻的血跡脚步声）',
    'door_open': '（吱呀……推拉门缓缓滑开）',
    'door_close': '（咔哒……推拉门滑回原位）',
    'clock_tick': '（滴答……滴答……老旧的挂钟还在走）',
    'thunderstorm': '【雷雨】轰隆——（远处的雷声与淅沥的雨声）',
    'water_drip': '（嗒……嗒……停尸房角落的水滴声）',
}


def play_sfx(name, volume=1.0, pitch=None):
    """播放一次性音效（★ 播放调用严格 try-except，绝不因音频闪退）：
    加载失败时 load_audio 已 print 警告；播放失败同样 print 警告并退化为
    文字音效占位，游戏继续运行。★ 每次播放都记入 SFX_LOG（测试断言用）"""
    SFX_LOG.append(name)
    if len(SFX_LOG) > 64:
        del SFX_LOG[:-64]
    if active_modifier and active_modifier.get('quiet'):
        volume *= 0.6
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
        # ★ 播放失败（设备/驱动等）：print 警告并继续，绝不闪退
        print(f'警告：未找到音频文件 {name}（或播放失败）')
        print(SOUND_TEXT.get(name, f'（音效：{name}）'))


# =====================================================================================
#  ★ 随机背景音乐系统（Random BGM，规格一）：
#    每次进入 'PLAYING'（进入关卡）时调用 play_random_bgm()——
#    用 random.choice() 从 assets/sounds/ 下的 bgm_random_1~3.mp3 中随机选一首
#    循环播放（loop=True）。全部 try-except：用户未提供这些文件时 print 提示
#    并回退到内置合成 BGM，游戏照常运行，绝不闪退。
# =====================================================================================
def play_random_bgm():
    """★ 随机 BGM：随机选一首 bgm_random_X.mp3 循环播放（规格）。
    文件缺失/加载失败 → print("提示：未找到音频文件 xxx") 并回退内置合成 BGM。"""
    global bgm_audio
    chosen = random.choice(BGM_RANDOM_FILES)
    path = os.path.join(SOUND_DIR, chosen)   # assets/sounds/bgm_random_X.mp3
    try:
        try:
            if bgm_audio is not None:
                bgm_audio.stop()             # 先停掉上一首（含合成兜底 BGM）
        except Exception:
            pass
        if not os.path.isfile(path):
            raise FileNotFoundError(path)    # 文件不存在 → 走回退分支
        # ★ 规格写法：循环播放（loop=True）、不自动播放
        bgm_audio = Audio(path, loop=True, volume=0.32, autoplay=False)
        bgm_audio.play()
        print(f'✅ 音频加载成功: {chosen}（随机 BGM，loop=True）')
    except Exception:
        # ★ 文件缺失/加载失败：❌ 红色警告，回退内置合成 BGM（静音运行也不闪退）
        print(f'\033[91m❌ 严重警告: 未找到音频 {path}——已回退内置合成 BGM\033[0m')
        try:
            if _synth_bgm_backup is not None:
                bgm_audio = _synth_bgm_backup
                bgm_audio.volume = 0.32
                bgm_audio.play()
                print('（已回退到内置合成 BGM）')
        except Exception:
            pass


# =====================================================================================
#  ★ 随机惊吓环境音效（Random Scare Ambience，规格二）：
#    每 15~45 秒随机触发一次 play_random_scare()——随机选一首惊吓音，
#    以 is_3d=True 加载，并在玩家周围 15~30 米的随机位置发出
#    （模拟远处传来的诡异声音）。全部 try-except：文件缺失时 print 提示并
#    静音运行，绝不闪退。计时器在全局 update() 中推进——暂停/菜单时不计时。
# =====================================================================================
def play_random_scare():
    """★ 随机惊吓音：随机选一首 → is_3d=True 加载 → 在玩家周围 15~30 米的
    随机位置发出（规格）。文件缺失 → print("提示：未找到音频文件 xxx") 并静音。"""
    if player is None:
        return
    chosen = random.choice(SCARE_RANDOM_FILES)
    path = os.path.join(SOUND_DIR, chosen)   # assets/sounds/sfx_scare_x.mp3
    # ★ 随机位置：以玩家为圆心、15~30 米、随机方向（随机向量），高度 1.5 米
    ang = random.uniform(0, math.tau)
    dist = random.uniform(15.0, 30.0)
    pos = Vec3(player.x + math.cos(ang) * dist, 1.5,
               player.z + math.sin(ang) * dist)
    # ---- 生命周期管理：清掉已播完的旧惊吓音，防止 Audio 对象累积 ----
    for old in list(scare_audio_pool):
        try:
            if not old.playing:
                old.stop()
                scare_audio_pool.remove(old)
        except Exception:
            try:
                scare_audio_pool.remove(old)
            except Exception:
                pass
    try:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)    # 文件不存在 → 走静音提示分支
        try:
            # ★ 规格写法：is_3d=True 加载（一次性播放，不循环）
            aud = Audio(path, loop=False, volume=0.85, autoplay=False,
                        is_3d=True)
        except TypeError:
            # 老版本不支持 is_3d 参数：退化为普通音效（音量已按"远处的声音"调低）
            aud = Audio(path, loop=False, volume=0.5, autoplay=False)
        try:
            set_audio_position(aud, pos)     # ★ 声音从远处随机位置发出
        except Exception:
            pass
        aud.play()
        scare_audio_pool.append(aud)
        print(f'【惊吓】远处传来诡异的声音……（{chosen}，来自 {dist:.0f} 米外）')
    except Exception:
        # ★ 文件缺失/加载失败：❌ 红色警告（规格），游戏静音运行，绝不闪退
        print(f'\033[91m❌ 严重警告: 未找到音频 {path}（随机惊吓静音跳过）\033[0m')


# =====================================================================================
#  三、局外存档：代币 / 永久技能 / 设置（json 持久化）
# =====================================================================================
SAVE = {'fragments': 0, 'settings': {'sensitivity': 40.0}}


def load_save():
    global SAVE
    try:
        with open(SAVE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        pass                                    # 碎片进度已迁移至 save_data.json
        SAVE['settings']['sensitivity'] = float(
            data.get('settings', {}).get('sensitivity', 40.0))
    except Exception:
        pass


def write_save():
    try:
        with open(SAVE_PATH, 'w', encoding='utf-8') as f:
            json.dump(SAVE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'（存档写入失败：{e}）')


# ★ 规格一：觉醒系统已删除——以下为固定规则（不再有永久技能）
def get_start_lives():
    """生命上限（固定 3）"""
    return START_LIVES


def get_echo_cooldown():
    """回声冷却（固定 5 秒）"""
    return ECHO_COOLDOWN_BASE


def walk_is_silent():
    """脚步永远有声（静音鞋随觉醒系统一并移除）"""
    return False


# =====================================================================================
#  四、怪物模型查找（★ 规格路径：assets/models/model_monster.obj）：
#    assets/models/model_monster.obj → assets/models/monster.obj（旧缓存，兼容）→
#    网络下载（保存为 assets/models/model_monster.obj）→ 组合模型兜底。
#    全程 try-except：找不到模型时 print 警告并使用代码拼凑的怪物，绝不闪退。
# =====================================================================================
MONSTER_OBJ_URL = ('https://raw.githubusercontent.com/mrdoob/three.js/dev/'
                   'examples/models/obj/male02/male02.obj')
MONSTER_MODEL_PATH = os.path.join(MODEL_DIR, 'model_monster.obj')   # ★ 规格路径


def try_download_monster_model():
    """尝试网络下载怪物模型到 assets/models/model_monster.obj（6 秒超时，try-except 兜底）"""
    dest = MONSTER_MODEL_PATH
    if os.path.exists(dest):
        return dest
    tmp = dest + '.tmp'
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        req = urllib.request.Request(MONSTER_OBJ_URL,
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as resp, open(tmp, 'wb') as f:
            f.write(resp.read(8 * 1024 * 1024))
        if os.path.getsize(tmp) > 50 * 1024:
            os.replace(tmp, dest)
            print('（已下载网络怪物模型 assets/models/model_monster.obj）')
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
    """★ 按规格从 assets/models/model_monster.obj 加载怪物模型；
    找不到时 print 提示并返回 None（游戏使用代码拼凑的组合怪物，继续运行）。"""
    for path in (os.path.join(MODEL_DIR, 'monster_listener.glb'),  # ★ 规格一.1：聆听者 glb 优先
                 os.path.join(MODEL_DIR, 'monster_listener.obj'),  # ★ 聆听者 obj
                 MONSTER_MODEL_PATH,                              # 规格路径（向后兼容）
                 os.path.join(MODEL_DIR, 'monster.obj')):          # 旧版缓存
        if os.path.exists(path):
            print(f'✅ 模型加载成功: {os.path.basename(path)}')
            return path
    print('\033[91m❌ 模型加载失败，已降级为方块: assets/models/model_monster.obj '
          '未找到——使用代码拼凑组合怪物（黑细身体+红眼，可见不隐身）\033[0m')
    return try_download_monster_model()


MONSTER_OBJ_PATH = find_monster_model()


# =====================================================================================
#  ★ 通用模型加载链（规格七）：.glb → .obj → .png(Billboard) → 组合模型兜底。
#    每一步都 try-except，彻底失败时红色打印错误并返回 None（调用方使用组合模型）。
# =====================================================================================
_MODEL_OK_LOGGED = set()


def _log_model_ok(path):
    """✅ 模型加载成功日志（同名只记录一次，防刷屏）"""
    key = os.path.basename(path)
    if key not in _MODEL_OK_LOGGED:
        _MODEL_OK_LOGGED.add(key)
        print(f'✅ 模型加载成功: {key}')


def load_model_safe(base_name, entity_class=Entity, **entity_kwargs):
    """★ 安全模型加载链（规格七）：
    1. 尝试加载 assets/models/{base_name}.glb
    2. 失败则尝试 assets/models/{base_name}.obj
    3. 失败则尝试 assets/models/{base_name}.png（Billboard 永远面向摄像机）
    4. 全部失败 → 返回 None（调用方使用组合模型兜底），绝不闪退。
    base_name 不含扩展名。"""
    for ext, is_billboard in (('.glb', False), ('.obj', False), ('.png', True)):
        path = os.path.join(MODEL_DIR, base_name + ext)
        if not os.path.isfile(path):
            continue
        try:
            if is_billboard:
                e = entity_class(model='quad', **entity_kwargs)
                try:
                    e.texture = path
                except Exception:
                    pass
                e.is_billboard = True
                _log_model_ok(path)
                return e
            else:
                e = entity_class(model=path, **entity_kwargs)
                _log_model_ok(path)
                return e
        except Exception as ex:
            print(f'\033[91m[错误] 模型格式解析失败: {path} → {ex}\033[0m')
            continue
    print(f'\033[91m❌ 模型加载失败，已降级为方块: assets/models/{base_name}.glb/.obj/.png '
          f'均未找到——使用代码拼凑组合模型兜底\033[0m')
    return None


def find_prop_model(base_name):
    """★ 道具模型查找（规格七）：.glb → .obj → .png → None。
    返回路径或 None。 None 时调用方使用灰色方块兜底（绝不闪退或隐身）。"""
    for ext in ('.glb', '.obj', '.png'):
        path = os.path.join(MODEL_DIR, base_name + ext)
        if os.path.isfile(path):
            _log_model_ok(path)
            return path
    print(f'\033[91m❌ 模型加载失败，已降级为方块: assets/models/{base_name}'
          f'.glb/.obj/.png 均未找到（方块可见可交互，绝不隐身）\033[0m')
    return None

# =====================================================================================
#  五、通用工具（含 ★ 楼梯/地形高度检测——"楼梯走不了"修复核心）
# =====================================================================================
def entity_gate(entity):
    """★ 防闪退闸门（规格）：所有实体 update() 第一行必须判定——
    实体未构造完成（initialized 未置位）或全局状态非 PLAYING 时一律跳过。
    initialized 在各实体 __init__ 的最后一行才置位：若构造中途抛异常，
    残缺实体永远不会被 update 触碰，从根上杜绝初始化期闪退。"""
    return game_state == GameState.PLAYING and getattr(entity, 'initialized', False)


def dist_xz(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def add_box_collider(entity, center=None, size=None):
    """★ 规格要求：给实体附加 Box 碰撞体（显式 center/size，try-except 防闪退）。
    ★ 关键修正（实测发现）：BoxCollider 挂在实体节点下，其 size/center 会被
    实体的 scale 再次缩放——期望的世界尺寸必须先除以实体 scale，
    否则碰撞体会被放大数倍（例如平台 scale 4 × size 4 = 实际 16）。"""
    try:
        s = entity.scale
        try:
            sx, sy, sz = float(s[0]), float(s[1]), float(s[2])
        except Exception:
            sx = sy = sz = float(s)
        size = size or Vec3(1, 1, 1)
        corrected = Vec3(size[0] / max(abs(sx), 1e-6),
                         size[1] / max(abs(sy), 1e-6),
                         size[2] / max(abs(sz), 1e-6))
        # center 同样处于被缩放的本地空间（地面等 y 缩放为 1 时无需修正）
        c = center or Vec3(0, 0, 0)
        corrected_center = Vec3(c[0] / max(abs(sx), 1e-6),
                                c[1] / max(abs(sy), 1e-6),
                                c[2] / max(abs(sz), 1e-6))
        entity.collider = BoxCollider(entity, center=corrected_center,
                                      size=corrected)
    except Exception:
        entity.collider = None


_ALL_TRACKED = (WALLS, MONSTERS, SPIDERS, CROWS, SONARS, DIARIES, CABINETS, PIPES,
                FUSES, STONES, ECHO_SPHERES, RIPPLES, RAMPS, PLATFORMS,
                DOORS, WARNING_LIGHTS, BLOODPOOLS, MIRRORS, TANKS, TABLES,
                REPORTS, KEYCARDS, MAIN_DOORS, AMBIENT_SOUNDS3D, WALKABLES)


def safe_destroy(entity):
    """★ 销毁铁律：is_dead=True → 从所有追踪列表 remove() → destroy()。
    任何 None / 已销毁实体直接返回，杜绝空指针报错。"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    entity.is_dead = True
    for lst in _ALL_TRACKED:
        if entity in lst:
            lst.remove(entity)
    try:
        destroy(entity)
    except Exception:
        pass          # 销毁失败不致命：is_dead 已标记，所有判定都会过滤它


def emit_noise(position, radius):
    """噪音事件广播给所有聆听者"""
    for m in list(MONSTERS):                    # ★ 浅拷贝遍历
        if getattr(m, 'is_dead', False):
            continue
        m.hear_noise(position, radius)


def find_safe_spawn():
    """★ 安全重生点选择（规格二）：从 spawn_points 随机选取一个
    距所有怪物 ≥15 米的安全点。最多重试 10 次；
    全部不安全时返回距怪物最远的候选点（仍优于原地重生）。"""
    if not spawn_points:
        return None
    best_pos = None
    best_dist = -1.0
    for _ in range(10):
        cand = random.choice(spawn_points)
        min_d = 1e9
        for m in list(MONSTERS):
            if getattr(m, 'is_dead', False):
                continue
            d = dist_xz(m.position, cand)
            if d < min_d:
                min_d = d
        if min_d >= 15.0:
            return cand
        if min_d > best_dist:
            best_dist = min_d
            best_pos = cand
    return best_pos


def resolve_collisions(entity, radius):
    """圆形实体 vs 墙体 AABB 推出（防穿墙，含 Y 层级检测——双层地图不互相干扰）"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    reach = TILE + radius
    entity_bottom = entity.y - 0.3
    entity_top = entity.y + 2.0
    for wall in list(WALLS):
        if wall.is_dead:
            continue
        if abs(wall.x - entity.x) > reach or abs(wall.z - entity.z) > reach:
            continue
        # ★ Y 层级检测：墙体与实体在 Y 轴上无重叠则跳过
        wall_bottom = wall.y - wall.scale[1] / 2.0
        wall_top = wall.y + wall.scale[1] / 2.0
        if entity_top < wall_bottom or entity_bottom > wall_top:
            continue
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        nearest_x = clamp(entity.x, wall.x - hx, wall.x + hx)
        nearest_z = clamp(entity.z, wall.z - hz, wall.z + hz)
        dx = entity.x - nearest_x
        dz = entity.z - nearest_z
        dist_sq = dx * dx + dz * dz
        if dist_sq >= radius * radius:
            continue
        if dist_sq <= 1e-9:
            overlap_x = hx - abs(entity.x - wall.x)
            overlap_z = hz - abs(entity.z - wall.z)
            if overlap_x <= overlap_z:
                entity.x = wall.x + (hx + radius) * (1 if entity.x >= wall.x else -1)
            else:
                entity.z = wall.z + (hz + radius) * (1 if entity.z >= wall.z else -1)
        else:
            dist = math.sqrt(dist_sq)
            push = radius - dist
            entity.x += dx / dist * push
            entity.z += dz / dist * push


def push_out_if_stuck(entity):
    """★ 卡墙保护：实体中心陷入墙体 → 强行传送到最近开阔地"""
    if entity is None or getattr(entity, 'is_dead', False):
        return False
    for wall in list(WALLS):
        if wall.is_dead:
            continue
        if abs(wall.x - entity.x) > TILE or abs(wall.z - entity.z) > TILE:
            continue
        # ★ Y 重叠检查：地下室墙体（Y -5~-1）不能把地面（Y 0）上的实体判为卡墙
        #   ——否则地下室南壁（横贯走廊 z=8）的 XZ 足印会把走向竖井的玩家
        #   永久推回开阔点，楼梯根本无法下行（三层地图核心回归）。
        hy = wall.scale[1] / 2.0
        if wall.y + hy < entity.y - 0.3 or wall.y - hy > entity.y + 1.8:
            continue
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        if abs(entity.x - wall.x) < hx and abs(entity.z - wall.z) < hz:
            world = level_manager.nearest_open_point(entity.position)  # ★ 兼容 L3（无网格）
            entity.x = world.x
            entity.z = world.z
            return True
    return False


def get_ground_height(x, z, current_y):
    """★ 脚下地形高度（"楼梯走不了"+"下楼逻辑"修复核心）：
    解析法三层判定，天然支持 Y 轴【上升与下降】：
      ① 楼梯斜坡优先：斜坡覆盖区内直接返回解析高度（上/下行都平滑），
         且只接受"不高于头顶容差"的表面——行走经过楼梯下方时不会被瞬移上梯；
      ② 可行走 AABB（地面/平台/地下室地板，注册于 WALKABLES）：
         取"不高于当前 y + 0.65 米步高容差"的最高表面——
         地下室(Y=-5)行走时，头顶的 Y=0 地面会被容差过滤掉，不会把人拉上去；
      ③ 射线检测兜底（同样带 y 过滤），再不行返回 0（迷宫地面）。
    玩家 y 由 update() 的 lerp 平滑逼近返回值——下降时同样平滑，不掉穿地板。"""
    tolerance = 0.65                      # 步高容差（台阶单级 < 0.5 米）

    # ---- ① 楼梯斜坡优先（区域内唯一权威表面）----
    # 接受条件：斜坡高度与当前 y 的差在 [-1.5, +0.65] 内——
    #   +0.65 = 上楼梯的步高容差；-1.5 = 下楼梯时逐帧平滑跟随（不能更大，
    #   否则地面行走经过竖井正上方时会被斜坡"吸"下去）。
    for r in list(RAMPS):
        if r.is_dead:
            continue
        try:
            h = r.height_at(x, z)
        except Exception:
            h = None
        if h is not None and -1.5 <= (h - current_y) <= 0.65:
            return h

    # ---- ② 可行走 AABB 表面：取容差内的最高者 ----
    best = None
    for w in list(WALKABLES):
        if getattr(w, 'is_dead', False):
            continue
        if abs(x - w.x) <= w.scale[0] / 2.0 and abs(z - w.z) <= w.scale[2] / 2.0:
            top = w.walk_top
            if top <= current_y + tolerance and (best is None or top > best):
                best = top
    if best is not None:
        return best

    # ---- ③ 射线检测兜底（带 y 过滤：命中点不得高于头顶容差）----
    try:
        origin_y = current_y + 2.0
        hit = raycast(Vec3(x, origin_y, z), Vec3(0, -1, 0), distance=12.0,
                      ignore=(player,) if player is not None else ())
        if hit is not None and getattr(hit, 'entity', None) is not None \
                and getattr(hit.entity, 'is_terrain', False) \
                and hit.world_point.y <= current_y + tolerance:
            return hit.world_point.y
    except Exception:
        pass
    return 0.0                            # 默认迷宫地面


def set_wireframe(entity, on):
    """切换线框/实心渲染（规格 wireframe 属性 + Panda 底层接口，双保险）"""
    try:
        entity.wireframe = on
    except Exception:
        pass
    try:
        if on:
            entity.set_render_mode_wireframe(2)
        else:
            entity.set_render_mode_filled(2)
    except Exception:
        pass


def apply_lit_shader(entity):
    if lit_shader is not None:
        try:
            entity.shader = lit_shader
        except Exception:
            pass


def clear_shader(entity):
    try:
        entity.shader = None
    except Exception:
        pass


class Stairs(Entity):
    """★ 可行走楼梯（"楼梯走不了"+"向下楼梯"修复）：
    视觉上是一排台阶（每级都是带 BoxCollider 的立方体），
    逻辑上注册为一段斜坡（height_at 给出任意点的解析高度）。
    玩家 update 通过 get_ground_height() 取得脚下高度，再用
    lerp(player.y, target_y, time.dt * 10) 平滑升降——完全不依赖物理引擎。
    ★ rise 支持负值：负 rise = 向下延伸的楼梯（台阶为悬空薄板，逐级沉入
      地下室）；正 rise = 向上的实心台阶（L2 平台用）。"""

    def __init__(self, base_x, base_z, base_y, rise, run, width,
                 direction='+z', step_count=6, color_rgb=(10, 10, 10)):
        """base_x/base_z/base_y：楼梯底端中心；rise：总升高（负=向下走）；
        run：水平总长；width：宽度；direction：走向('+z'/'-z'/'+x'/'-x')"""
        super().__init__(position=(base_x, base_y, base_z))
        self.is_dead = False
        self.is_terrain = True                  # ★ 射线检测认定地形
        self.rise = rise
        self.run = max(run, 0.001)
        self.base_y = base_y
        self.width = width
        self.ax, self.az = {'+z': (0, 1), '-z': (0, -1),
                            '+x': (1, 0), '-x': (-1, 0)}[direction]
        # ---- 视觉台阶：每级一个立方体 + BoxCollider（规格要求）----
        self.steps = []
        for i in range(step_count):
            t0 = i / step_count
            t1 = (i + 1) / step_count
            step_top = base_y + rise * t1       # 该级台阶的顶面高度（可正可负）
            depth = self.run / step_count
            sx = depth if self.ax != 0 else width               # 沿行走方向的厚度
            sz = depth if self.az != 0 else width
            cx = base_x + self.ax * self.run * (t0 + t1) / 2    # 台阶中心（世界坐标）
            cz = base_z + self.az * self.run * (t0 + t1) / 2
            if rise >= 0:
                # 上升楼梯：实心台阶，从本级顶面向下垫到地面以下
                h = max(step_top - base_y, 0.05) + 0.6
                cy = step_top - h / 2
            else:
                # ★ 下降楼梯：悬空薄板台阶（顶面在本级高度，向下 0.6 米厚）
                h = 0.6
                cy = step_top - h / 2
            step = Entity(parent=self, model='cube',
                          position=(cx - base_x, cy - 0.0, cz - base_z),
                          scale=(sx, h, sz),
                          color=color.rgb(*color_rgb))
            step.is_dead = False
            step.is_terrain = True                              # ★ 射线检测认定地形
            step.is_stair_step = True                           # ★ 规格一.1：台阶不算绕障障碍
            add_box_collider(step, size=Vec3(sx, h, sz))
            apply_lit_shader(step)
            self.steps.append(step)
        RAMPS.append(self)                                      # 注册解析斜坡

    def height_at(self, x, z):
        """解析斜坡高度：沿上升方向 0→run 线性从 base_y 升到 base_y+rise；
        超出楼梯范围（含左右超出宽度）返回 None。"""
        dx = x - self.x
        dz = z - self.z
        along = dx * self.ax + dz * self.az          # 沿上升轴的距离
        side = dx * (-self.az) + dz * self.ax        # 垂直于上升轴的偏移
        if along < -0.2 or along > self.run + 0.2:
            return None
        if abs(side) > self.width / 2 + 0.15:
            return None
        t = clamp(along / self.run, 0.0, 1.0)
        return self.base_y + self.rise * t


def build_slab_with_holes(x_lo, x_hi, z_lo, z_hi, holes, top_y, thick=1.0):
    """★ 全尺寸二楼楼板（规格三.1）：在 x∈[x_lo,x_hi]、z∈[z_lo,z_hi] 范围内
    铺设 top_y 顶面楼板，holes=[(x0,x1,z0,z1)] 为楼梯洞口（洞内完全开孔）。
    z 向按洞口边缘切条带、条带内按洞口 x 区间分段——洞口边缘精确对齐，
    绝不留玩家可坠落的细缝。全部走 build_platform（注册 WALKABLES，含碰撞体）。"""
    edges = {z_lo, z_hi}
    for (_, _, z0, z1) in holes:
        edges.add(max(z_lo, min(z_hi, z0)))
        edges.add(max(z_lo, min(z_hi, z1)))
    zs = sorted(edges)
    for z0, z1 in zip(zs, zs[1:]):
        if z1 - z0 < 0.05:
            continue
        cuts = []
        for (hx0, hx1, hz0, hz1) in holes:
            if hz0 <= z0 + 0.01 and hz1 >= z1 - 0.01:   # 洞口完整覆盖该条带
                cuts.append((max(hx0, x_lo), min(hx1, x_hi)))
        cuts.sort()
        segs, cur = [], x_lo
        for (a, b) in cuts:
            if a > cur + 0.05:
                segs.append((cur, a))
            cur = max(cur, b)
        if cur < x_hi - 0.05:
            segs.append((cur, x_hi))
        for (a, b) in segs:
            build_platform((a + b) / 2, (z0 + z1) / 2, top_y,
                           b - a, z1 - z0, thick=thick)


def build_platform(cx, cz, top_y, size_x=4.0, size_z=4.0, thick=None):
    """★ 搭建一块可行走的平台/地板（顶面高度 = top_y，支持负高度——地下室地板）：
    视觉立方体 + BoxCollider + 地形标记，并注册进 WALKABLES 供
    get_ground_height 的解析判定使用（含 walk_top 顶面高度）。
    top_y >= 0：默认实心柱体垫到平台顶（可传 thick 指定板厚——二层夹层）；
    top_y < 0：1 米厚平板（地下室地板）。"""
    if thick is None:
        thick = top_y + 0.5 if top_y >= 0 else 1.0   # 默认：实心柱 / 地下室平板
    plat = Entity(model='cube',
                  position=(cx, top_y - thick / 2, cz),
                  scale=(size_x, thick, size_z),
                  color=color.rgb(8, 8, 8))         # ★ 规格一.2：平台/楼板极暗深灰
    plat.is_dead = False
    plat.is_terrain = True
    plat.walk_top = top_y                 # ★ 顶面高度（解析判定用）
    add_box_collider(plat, size=Vec3(size_x, thick, size_z))
    apply_lit_shader(plat)
    PLATFORMS.append(plat)
    WALKABLES.append(plat)
    return plat


# =====================================================================================
#  六、迷宫生成：DFS 递归回溯 + 随机打墙（参数化尺寸：第一关 40 / 第二关 30）
# =====================================================================================
def generate_maze_grid(grid_n=GRID_L1):
    """DFS 递归回溯生成 grid_n×grid_n 二维数组迷宫（0=路，1=墙），
    之后随机打通一部分非边界墙制造环路与十字路口。"""
    grid = [[1] * grid_n for _ in range(grid_n)]
    max_odd = grid_n - 3
    grid[1][1] = 0
    stack = [(1, 1)]
    while stack:
        x, z = stack[-1]
        neighbors = []
        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, nz = x + dx, z + dz
            if 1 <= nx <= max_odd and 1 <= nz <= max_odd and grid[nz][nx] == 1:
                neighbors.append((nx, nz))
        if neighbors:
            nx, nz = random.choice(neighbors)
            grid[z + (nz - z) // 2][x + (nx - x) // 2] = 0
            grid[nz][nx] = 0
            stack.append((nx, nz))
        else:
            stack.pop()
    opened = 0
    for z in range(1, grid_n - 1):
        for x in range(1, grid_n - 1):
            if grid[z][x] == 1:
                horiz = grid[z][x - 1] == 0 and grid[z][x + 1] == 0
                vert = grid[z - 1][x] == 0 and grid[z + 1][x] == 0
                if (horiz ^ vert) and random.random() < BRAID_RATIO:
                    grid[z][x] = 0
                    opened += 1
    print(f'（迷宫已生成：{grid_n}x{grid_n} 地块 | 随机打通 {opened} 面墙形成环路）')
    return grid


# =====================================================================================
#  七、实体类（全部继承 Entity；update() 第一行均为状态闸门）
# =====================================================================================
class Revealable(Entity):
    """可被回声照亮的实体基类：平时黑色实心；被声波扫中切换为高亮青白线框
    （rgba(0,255,255,200)）持续 1.5 秒，随后 invoke 延迟恢复。"""

    REVEAL_COLOR = color.rgba(0, 255, 255, 255)   # ★ 规格二.1：不透明高亮青白（wireframe 显形）

    def __init__(self, base_color=color.rgb(0, 0, 0), **kwargs):
        super().__init__(color=base_color, **kwargs)
        self.is_dead = False
        self.base_color = base_color

    def reveal(self):
        if getattr(self, 'is_dead', False):
            return
        # ★ 规格一：体积高亮交给幽灵方块——本体保持极暗材质（不再线框）
        _register_echo_reveal(self)


def _spawn_echo_ghost(e, rgb=(0, 255, 255)):
    """★ 规格二：生成与目标同尺寸（×1.02 防遮挡放大）的纯线框实体。
    墙壁/布景 = 极耀眼纯青 rgb(0,255,255)；怪物 = 纯红（Monster.reveal 传入）。
    Alpha 恒 255（绝对清晰）；生成后 animate_color 8 秒平滑淡出至透明。
    独立实体方案：不缩放墙本体（防碰撞体外扩）、不生成实心方块。"""
    try:
        if isinstance(e, Monster):
            pos = e.world_position + Vec3(0, 1.6, 0)
            sc = (1.3 * 1.02, 3.3 * 1.02, 1.3 * 1.02)   # 怪物包围盒近似
        else:
            ws = e.world_scale
            pos = e.world_position
            sc = (ws[0] * 1.02, ws[1] * 1.02, ws[2] * 1.02)
        ghost = Entity(model='cube',
                       color=color.rgba(rgb[0], rgb[1], rgb[2], 255),
                       position=pos, scale=sc)
        set_wireframe(ghost, True)              # ★ 规格二.1：纯线框模式
        try:
            ghost.setFogOff()                   # ★ 线框豁免雾效——30 米内依然耀眼
        except Exception:
            pass
        ghost.life = REVEAL_DURATION
        ghost._auto_anim = False
        # ★ 规格二.4：animate_color 8 秒淡出（保持亮眼→平滑消失）
        try:
            ghost.animate_color(color.rgba(rgb[0], rgb[1], rgb[2], 0),
                                duration=REVEAL_DURATION)
            ghost._auto_anim = True
        except Exception:
            pass                                # 兜底：由 update 循环逐帧淡出
        ECHO_GHOSTS.append(ghost)
        if not hasattr(e, '_echo_ghosts') or e._echo_ghosts is None:
            e._echo_ghosts = []
        e._echo_ghosts.append(ghost)
        return ghost
    except Exception:
        return None


def _register_echo_reveal(e, rgb=(0, 255, 255)):
    """★ 规格二：回声线框登记——1.02 放大线框实体 + invoke 精确 8 秒销毁/复位；
    令牌守卫防旧定时器扑灭新回声；墙本体保持极暗材质（绝不用实心方块代替墙）。"""
    e._reveal_token = getattr(e, '_reveal_token', 0) + 1
    e.reveal_t = REVEAL_DURATION
    _spawn_echo_ghost(e, rgb)
    if e not in ECHO_FADE:
        ECHO_FADE.append(e)
    invoke(_echo_restore, e, e._reveal_token, delay=REVEAL_DURATION)


def _echo_restore(e, token):
    """★ 8 秒定时恢复（规格一）：销毁幽灵方块 + 墙体模式复位；
    令牌守卫防新回声被旧定时器提前扑灭。"""
    if e is None:
        return
    if getattr(e, '_reveal_token', 0) != token:
        return
    for g in (getattr(e, '_echo_ghosts', None) or []):
        try:
            if g in ECHO_GHOSTS:
                ECHO_GHOSTS.remove(g)
            destroy(g)
        except Exception:
            pass
    e._echo_ghosts = None
    if getattr(e, 'is_dead', False):
        return
    if e in ECHO_FADE:
        ECHO_FADE.remove(e)
    if isinstance(e, Wall):
        # 显式恢复（绕开 set_dark 的 ECHO 模式守卫）
        if player is not None and dist_xz(e.position, player.position) <= WALL_SENSE_ENTER:
            e.enter_near()
            e.apply_near_alpha(1.0)
        else:
            e.mode = Wall.MODE_DARK
            e.near_alpha = 0.0
            e.color = e.base_color
            apply_lit_shader(e)
            set_wireframe(e, False)
    elif isinstance(e, Monster):
        _delayed_monster_restore(e)
    else:
        e.color = e.base_color
        apply_lit_shader(e)
        set_wireframe(e, False)


def _delayed_restore(entity):
    if entity is None or getattr(entity, 'is_dead', False):
        return
    entity.color = entity.base_color
    apply_lit_shader(entity)
    set_wireframe(entity, False)


class Wall(Revealable):
    """黑色迷宫墙：dark 近黑实心 / near 近距暗灰线框（平滑渐变+滞回）/ echo 青白线框"""

    BASE = color.rgb(8, 8, 8)         # ★ 规格一.2：极暗深灰墙（回声高亮不受影响）
    NEAR_R, NEAR_G, NEAR_B, NEAR_A = 50, 50, 50, 100
    MODE_DARK, MODE_NEAR, MODE_ECHO = 'dark', 'near', 'echo'

    def __init__(self, cx, cz):
        super().__init__(
            base_color=self.BASE, model='cube',
            position=(cx, WALL_HEIGHT / 2, cz), scale=(4, 4, 4),
        )
        self.mode = Wall.MODE_DARK
        self.near_alpha = 0.0
        self.is_terrain = True                  # ★ 地形标记（射线检测）
        apply_lit_shader(self)
        add_box_collider(self, size=Vec3(4, 4, 4))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def enter_near(self):
        self.mode = Wall.MODE_NEAR
        self.near_alpha = max(self.near_alpha, 0.05)
        self.color = color.rgba(Wall.NEAR_R, Wall.NEAR_G, Wall.NEAR_B, 5)
        clear_shader(self)
        set_wireframe(self, True)

    def set_dark(self):
        if self.is_dead or self.mode == Wall.MODE_ECHO:
            return
        self.mode = Wall.MODE_DARK
        self.near_alpha = 0.0
        self.color = self.BASE
        apply_lit_shader(self)
        set_wireframe(self, False)

    def apply_near_alpha(self, alpha):
        self.near_alpha = alpha
        a = max(4, int(Wall.NEAR_A * alpha))
        self.color = color.rgba(Wall.NEAR_R, Wall.NEAR_G, Wall.NEAR_B, a)

    def reveal(self):
        if getattr(self, 'is_dead', False):
            return
        self.mode = Wall.MODE_ECHO              # 近墙感知的模式标记（复位用）
        _register_echo_reveal(self)             # ★ 幽灵方块体积高亮


def _wall_restore(wall):
    if wall is None or getattr(wall, 'is_dead', False):
        return
    if wall.mode != Wall.MODE_ECHO:
        return
    if player is not None and dist_xz(wall.position, player.position) <= WALL_SENSE_ENTER:
        wall.enter_near()
        wall.apply_near_alpha(1.0)
    else:
        wall.set_dark()


class EchoSphere(Entity):
    """回声波：青白色线框球，1.5 秒膨胀到 scale 60（半径 30）"""

    def __init__(self, origin):
        super().__init__(
            model='sphere', wireframe=True,
            color=color.rgba(0, 255, 255, 110),
            position=origin, scale=0.01, double_sided=True,
        )
        self.is_dead = False
        self.wave_origin = Vec3(origin.x, origin.y, origin.z)
        self.elapsed = 0.0
        self.revealed = set()
        try:
            self.set_render_mode_filled_wireframe(2)
        except Exception:
            try:
                self.set_render_mode_wireframe(2)
            except Exception:
                pass
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def _wave_reaches(self, wall, radius):
        hx = wall.scale[0] / 2.0
        hz = wall.scale[2] / 2.0
        nearest_x = clamp(self.wave_origin.x, wall.x - hx, wall.x + hx)
        nearest_z = clamp(self.wave_origin.z, wall.z - hz, wall.z + hz)
        dx = self.wave_origin.x - nearest_x
        dz = self.wave_origin.z - nearest_z
        return (dx * dx + dz * dz) <= radius * radius

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        self.elapsed += time.dt
        ratio = min(self.elapsed / ECHO_DURATION, 1.0)
        self.scale = ECHO_MAX_SCALE * ratio
        radius = self.scale / 2.0
        for wall in list(WALLS):
            if wall.is_dead or wall in self.revealed:
                continue
            if self._wave_reaches(wall, radius):
                wall.reveal()
                self.revealed.add(wall)
        for m in list(MONSTERS):
            if m.is_dead or m in self.revealed:
                continue
            if dist_xz(self.wave_origin, m.position) <= radius:
                m.reveal()
                self.revealed.add(m)
        # ★ 扫描破碎的镜子：触发一次特殊的高频玻璃音（第三关专属）
        for mir in list(MIRRORS):
            if mir.is_dead or mir in self.revealed:
                continue
            if dist_xz(self.wave_origin, mir.position) <= radius:
                mir.reveal()
                self.revealed.add(mir)
                play_sfx('glass', volume=0.7)
        # ★ 扫描玻璃培养罐：反弹沉闷的回音（第三关专属）
        for tk in list(TANKS):
            if tk.is_dead or tk in self.revealed:
                continue
            if dist_xz(self.wave_origin, tk.position) <= radius:
                tk.reveal()
                self.revealed.add(tk)
                play_sfx('tank_echo', volume=0.6)
        for pp in list(DRIP_PIPES):                  # ★ 规格二.3：管道回声显形
            if pp.is_dead or pp in self.revealed:
                continue
            if dist_xz(self.wave_origin, pp.position) <= radius:
                pp.reveal()
                self.revealed.add(pp)
        for eb in list(ELEC_BOXES):                  # ★ 规格二.3：配电箱回声显形
            if eb.is_dead or eb in self.revealed:
                continue
            if dist_xz(self.wave_origin, eb.position) <= radius:
                eb.reveal()
                self.revealed.add(eb)
        if self.elapsed >= ECHO_DURATION:
            self.is_dead = True


class GroundRipple(Entity):
    """地面声呐波纹：贴地发光青色线框圆环，迅速扩大并淡出（伪声呐/管子同样复用）。
    高度取所在位置的地形高度——楼梯/平台上也能正确贴地。"""

    DURATION = 1.1
    MAX_SCALE = 56.0

    def __init__(self, origin):
        gy = get_ground_height(origin.x, origin.z,
                               origin.y if origin.y else 3.0)
        super().__init__(
            model='circle', color=color.rgba(0, 255, 255, 210),
            position=Vec3(origin.x, gy + 0.07, origin.z),
            rotation_x=90, scale=0.5, double_sided=True,
        )
        self.is_dead = False
        self.elapsed = 0.0
        try:
            self.set_render_mode_wireframe(2)
        except Exception:
            pass
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self) or self.is_dead:
            return
        self.elapsed += time.dt
        r = min(self.elapsed / self.DURATION, 1.0)
        self.scale = 2.0 + (self.MAX_SCALE - 2.0) * (1.0 - (1.0 - r) ** 2)
        self.color = color.rgba(0, 255, 255, max(0, int(210 * (1.0 - r))))
        if self.elapsed >= self.DURATION:
            self.is_dead = True


def spawn_delayed_ripple(origin):
    if game_state == GameState.PLAYING:
        RIPPLES.append(GroundRipple(origin))


def spawn_delayed_noise(position, radius):
    """invoke 延迟的噪音广播（管子的多次假回声用）"""
    if game_state == GameState.PLAYING:
        emit_noise(position, radius)


class Stone(Entity):
    """投掷物：普通石头（噪音 18）或空管子（pipe=True：噪音 32 + 多次假回声）"""

    def __init__(self, position, direction, pipe=False):
        super().__init__(
            model='sphere' if not pipe else 'cube',
            color=color.rgb(20, 20, 22) if not pipe else color.rgb(70, 75, 85),
            position=position, scale=0.32,
        )
        self.is_dead = False
        self.pipe = pipe
        h = Vec3(direction.x, 0, direction.z)
        if h.length() < 0.01:
            h = Vec3(player.forward.x, 0, player.forward.z) if player else Vec3(0, 0, -1)
        self.velocity = h.normalized() * (STONE_SPEED * (0.9 if pipe else 1.0))
        self.flight_t = 0.0
        apply_lit_shader(self)
        add_box_collider(self, size=Vec3(0.3, 0.3, 0.3))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        dt = time.dt
        self.flight_t += dt
        self.position += self.velocity * dt
        self.y -= STONE_GRAVITY * self.flight_t * dt
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
            self._land()

    def _land(self):
        """落地：石头=一声闷响；★ 管子=更大的金属噪音 + 多次假回声（错峰波纹+噪音）"""
        pos = Vec3(self.position.x, 0, self.position.z)
        if self.pipe:
            play_sfx('pipe_land', volume=0.9, pitch=random.uniform(0.9, 1.1))
            emit_noise(pos, PIPE_NOISE)                    # 巨大落地噪音
            RIPPLES.append(GroundRipple(pos))              # 假回声 ×3（错峰）
            invoke(spawn_delayed_ripple, Vec3(pos.x, pos.y, pos.z), delay=0.4)
            invoke(spawn_delayed_ripple, Vec3(pos.x, pos.y, pos.z), delay=0.8)
            invoke(spawn_delayed_noise, Vec3(pos.x, pos.y, pos.z),
                   PIPE_NOISE * 0.8, delay=0.45)            # 二次噪音
            invoke(spawn_delayed_noise, Vec3(pos.x, pos.y, pos.z),
                   PIPE_NOISE * 0.6, delay=0.85)            # 三次噪音
        else:
            play_sfx('monster_step', volume=0.5)
            emit_noise(pos, STONE_NOISE)


def _cylinder_mesh(sides=10, radius=0.5, height=1.0):
    """★ 程序化圆柱网格（规格三.2）：Ursina 5.2 无内置 cylinder 模型
    （直接 model='cylinder' 会隐身），用 Mesh 手工构建十棱柱实体化。"""
    verts, tris = [], []
    half = height / 2.0
    rim_bot, rim_top = [], []
    for i in range(sides):
        a = math.tau * i / sides
        rim_bot.append((math.cos(a) * radius, -half, math.sin(a) * radius))
        rim_top.append((math.cos(a) * radius, half, math.sin(a) * radius))
    for v in rim_bot:
        verts.append(v)
    for v in rim_top:
        verts.append(v)
    for i in range(sides):                      # 侧面
        j = (i + 1) % sides
        tris += [(i, j, sides + j), (i, sides + j, sides + i)]
    c0 = len(verts)
    verts.append((0, half, 0))                  # 顶盖
    for i in range(sides):
        j = (i + 1) % sides
        tris.append((c0, sides + i, sides + j))
    mesh = Mesh(vertices=verts, triangles=tris)
    try:
        mesh.generate_normals()
    except Exception:
        pass
    return mesh


_FUSE_MESH = None                    # 全体保险丝共享一份程序化圆柱网格
_PIPE_MESH = None                    # 全体管道共享一份程序化圆柱网格


class Fuse(Entity):
    """发光保险丝（规格三.2）：实体圆柱体（程序化圆柱网格），
    淡黄色、规格尺寸 scale=(0.1,0.3,0.1)，近 10 米脉动 + 电流声"""

    def __init__(self, position):
        global _FUSE_MESH
        if _FUSE_MESH is None:
            _FUSE_MESH = _cylinder_mesh()
        super().__init__(
            model=_FUSE_MESH,
            position=position + Vec3(0, 0.3, 0),
            scale=(0.1, 0.3, 0.1),
            color=color.rgb(255, 230, 130),
        )
        # ★ 规格一.2：保险丝 3D 电流嗡鸣（靠近渐响，走远渐弱）
        AmbientSound3D(Vec3(position.x, position.y + 0.3, position.z),
                       'fuse_hum', base_volume=0.45, hear_range=8.0)
        self.is_dead = False
        self.near = False
        self.pulse_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.6, 1.5, 0.6))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        self.pulse_t += time.dt
        if self.near:
            b = 0.5 + 0.5 * math.sin(self.pulse_t * 4.0)
            self.scale = 0.5 + 0.08 * math.sin(self.pulse_t * 4.0)
            self.rotation_y += 90 * time.dt
        else:
            b = 0.35 + 0.35 * abs(math.sin(self.pulse_t * 1.8))
            self.scale = 0.5
            self.rotation_y += 45 * time.dt
        self.color = color.rgb(255, int(140 + 100 * b), int(30 + 60 * b))
        self.y = 0.7 + 0.1 * math.sin(self.pulse_t * 1.2)


class ExitGate(Entity):
    """出口门：第一关单门；第二关多门（is_real 标记真实出口，选错触发伏击）。
    第二关真实出口建在抬高平台上（gate_base_y 记录底面高度用于高度判定）"""

    def __init__(self, position, is_real=True):
        super().__init__(
            model='cube', position=position + Vec3(0, 1.5, 0),
            scale=(1.2, 3.0, 1.2), color=color.rgb(15, 40, 22),
        )
        self.is_dead = False
        self.is_real = is_real
        self.gate_base_y = position.y             # 门底面所在高度（平台判定用）
        self.locked = True
        self.ambushed = False                     # 假门是否已触发过伏击
        self.pulse_t = 0.0
        self.hint_cd = 0.0
        add_box_collider(self, size=Vec3(1.2, 3.0, 1.2))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        self.pulse_t += time.dt
        self.hint_cd = max(0.0, self.hint_cd - time.dt)
        if self.ambushed:                         # 已触发伏击的假门：转为暗红警示
            b = 0.6 + 0.4 * math.sin(self.pulse_t * 4.0)
            self.color = color.rgb(int(90 + 80 * b), 20, 20)
            return
        if self.locked:
            self.color = color.rgb(15, 40, 22)
        else:
            b = 0.65 + 0.35 * math.sin(self.pulse_t * 3.0)
            self.color = color.rgb(int(30 + 90 * b), int(150 + 105 * b), int(70 + 70 * b))

    def unlock(self):
        self.locked = False


class Diary(Entity):
    """日记本：微光书页，按 E 收集后弹出背景故事（全场冻结 3 秒自动合上）。
    glow_rgb 参数控制发光颜色：L2 蓝色（情感日记），L3 暖色（真相日记）。"""

    def __init__(self, position, text, glow_rgb=(185, 172, 140), frag_id=None):
        super().__init__(
            model='cube', position=position + Vec3(0, 0.35, 0),
            scale=(0.42, 0.1, 0.55), color=color.rgb(*glow_rgb),
        )
        self.is_dead = False
        # ★ 规格四.2/四.3：空文本容错——Text 必须拿到非空 display_text
        self.text = text if text else '这段记录已经被血迹模糊，无法辨认……'
        self.frag_id = frag_id              # ★ 绑定碎片池 ID（拾取时写入存档）
        self.glow_rgb = glow_rgb
        self.base_y = self.y                    # ★ 记录所在楼层高度（2F/夹层日记不落地）
        self.pulse_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.5, 0.3, 0.6))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        # 微弱的呼吸式泛光 + 轻微浮动，让玩家循光发现
        self.pulse_t += time.dt
        b = 0.5 + 0.5 * math.sin(self.pulse_t * 2.2)
        self.color = color.rgb(int(150 + 60 * b), int(140 + 55 * b), int(110 + 40 * b))
        self.y = self.base_y + 0.05 * math.sin(self.pulse_t * 1.5)


class Cabinet(Entity):
    """★ 储物柜（透孔观察修复版）：不再是一个封闭实心方块——由多块薄板拼成：
    背板 + 左右侧板 + 顶板 + 底板 + 两扇柜门（中间留一条竖直门缝）。
    玩家按 E 钻入后：碰撞体留在柜内，摄像机向柜门方向平滑前推（卡在门缝处），
    配合屏幕窥视遮罩，形成"透过柜门缝隙往外偷看"的视野。再按 E 离开。"""

    W, H, D, T = 1.3, 2.8, 1.1, 0.06      # 外形宽/高/深 与 板厚
    GAP = 0.14                            # ★ 两扇柜门中间的竖直门缝宽度

    def __init__(self, position, rotation_y=0):
        super().__init__(position=position, rotation_y=rotation_y)
        self.is_dead = False
        w, h, d, t = Cabinet.W, Cabinet.H, Cabinet.D, Cabinet.T
        wood = color.rgb(14, 11, 8)       # ★ 压暗柜体木色（防反光）
        dark = color.rgb(22, 16, 12)      # 柜内暗色（缝隙深处）
        # ---- 背板（本地 +z 侧）----
        Entity(parent=self, model='cube', position=(0, h / 2, d / 2 - t / 2),
               scale=(w, h, t), color=wood)
        # ---- 左右侧板 ----
        Entity(parent=self, model='cube', position=(-w / 2 + t / 2, h / 2, 0),
               scale=(t, h, d), color=wood)
        Entity(parent=self, model='cube', position=(w / 2 - t / 2, h / 2, 0),
               scale=(t, h, d), color=wood)
        # ---- 顶板 / 底板 ----
        Entity(parent=self, model='cube', position=(0, h - t / 2, 0),
               scale=(w, t, d), color=wood)
        Entity(parent=self, model='cube', position=(0, t / 2, 0),
               scale=(w, t, d), color=wood)
        # ---- 柜内衬板（暗色，透过门缝看到的"深处"）----
        Entity(parent=self, model='cube', position=(0, h / 2, 0.25),
               scale=(w - 0.1, h - 0.1, 0.02), color=dark)
        # ---- ★ 两扇柜门（本地 -z 侧），中间留竖直门缝 ----
        gap = Cabinet.GAP
        door_w = (w - gap) / 2
        for side in (-1, 1):
            door = Entity(parent=self, model='cube',
                          position=(side * (gap / 2 + door_w / 2), h / 2,
                                    -d / 2 + t / 2),
                          scale=(door_w, h, t), color=wood)
            apply_lit_shader(door)
            # 门上的横向装饰缝（细暗条——竖缝 + 横缝的木板门质感）
            for i in range(3):
                Entity(parent=self, model='cube',
                       position=(side * (gap / 2 + door_w / 2),
                                 0.6 + i * 0.8, -d / 2 - 0.005),
                       scale=(door_w - 0.12, 0.03, 0.01),
                       color=color.rgb(24, 17, 12))
        for p in self.children:
            p.is_dead = False
            p.is_terrain = False                  # 柜板不是地形：射线高度检测忽略
        add_box_collider(self, center=Vec3(0, h / 2, 0), size=Vec3(w, h, d))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）
        # 柜门朝向（rotation_y）：本地 -z 为门面方向——玩家钻入后面向此方向窥视
        self.door_yaw = rotation_y

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return


class PipeItem(Entity):
    """空管子（第二关）：按 E 拾取；F 投掷时优先使用——落地噪音更大且产生
    多次假回声（见 Stone._land 的 pipe 分支）。"""

    def __init__(self, position):
        super().__init__(
            model='cube', position=position + Vec3(0, 0.25, 0),
            scale=(0.12, 0.12, 1.3), rotation_y=random.uniform(0, 180),
            color=color.rgb(80, 85, 95),
        )
        self.is_dead = False
        self.pulse_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.3, 0.3, 1.4))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        self.pulse_t += time.dt
        b = 0.4 + 0.6 * abs(math.sin(self.pulse_t * 1.6))
        self.color = color.rgb(int(60 + 40 * b), int(65 + 40 * b), int(75 + 45 * b))


class Crow(Entity):
    """乌鸦：平时蹲伏不动；玩家靠近 <3 米惊飞——巨大扑腾声（噪音 25）吸引主怪"""

    STARTLE_DIST = 3.0
    FLAP_NOISE = 25.0

    def __init__(self, position):
        super().__init__(position=position + Vec3(0, 0.35, 0))
        self.is_dead = False
        self.startled = False
        self.body = Entity(parent=self, model='cube', scale=(0.28, 0.22, 0.4),
                           color=color.rgb(12, 12, 14), y=0.1)
        self.head = Entity(parent=self, model='sphere', scale=0.12,
                           position=(0, 0.28, -0.18), color=color.rgb(12, 12, 14))
        self.eye = Entity(parent=self, model='sphere', scale=0.03,
                          position=(0, 0.30, -0.26), color=color.rgb(255, 40, 40))
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead or self.startled:
            return
        if player is None or player.hidden:
            return
        # 高度判定：多层地形下，平台上/地面下的玩家不会惊飞乌鸦
        if abs(player.y - self.y) > 1.5:
            return
        if dist_xz(self.position, player.position) < Crow.STARTLE_DIST:
            self.startled = True
            play_sfx('flap', volume=0.9, pitch=random.uniform(0.9, 1.15))
            print('【乌鸦】扑棱棱——！！！乌鸦惊飞的巨响撕裂了黑暗！')
            emit_noise(self.position, Crow.FLAP_NOISE)       # 巨大噪音吸引主怪
            try:                                # 惊飞动画：快速拔高后飞离销毁
                self.animate_y(self.y + 5.0, duration=1.4, curve=curve.out_expo)
            except Exception:
                pass
            invoke(_crow_fly_away, self, delay=1.5)


def _crow_fly_away(crow):
    """乌鸦飞离后安全销毁（检查 is_dead 防闪退）"""
    if crow is not None and not getattr(crow, 'is_dead', False):
        safe_destroy(crow)


class SpiderSilk(Entity):
    """盲蛛丝线：横在走廊里的半透明细丝，玩家碰到（<0.65 米）即触发突脸致死。
    触发时本体变形为"蛛群之脸"完成突脸动画（多只红眼充满视野）。"""

    TRIGGER_DIST = 0.65

    def __init__(self, position, rotation_y=0):
        super().__init__(position=position, rotation_y=rotation_y)
        self.is_dead = False
        self.triggered = False
        # 丝线本体：细长半透明条，极难察觉（贴脸微光下隐约反光）
        self.silk = Entity(parent=self, model='cube',
                           scale=(3.6, 0.06, 0.05), y=1.0,
                           color=color.rgba(200, 200, 215, 26))
        # 突脸用的蛛眼（平时隐藏）
        self.eyes = []
        for i in range(8):
            ex = -0.28 + (i % 4) * 0.19
            ey = 1.95 + (0.12 if i >= 4 else 0.0)
            eye = Entity(parent=self, model='sphere', scale=0.06,
                         position=(ex, ey, -0.2), color=color.rgb(255, 30, 30),
                         enabled=False)
            self.eyes.append(eye)
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead or self.triggered:
            return
        if player is None or player.hidden:
            return
        if abs(player.y - self.y) > 1.5:
            return                              # ★ 玩家在地下室（低 5 米）不触发丝线
        # 丝线近似为一条线段（本地 X 轴向 ±1.8）：玩家到线段最近点距离判定
        dx = player.x - self.x
        dz = player.z - self.z
        c = math.cos(math.radians(self.rotation_y))
        s = math.sin(math.radians(self.rotation_y))
        local_x = dx * (-c) + dz * (s)          # 玩家偏移旋转到丝线本地坐标
        local_z = dx * (s) + dz * (c)
        nearest_x = clamp(local_x, -1.8, 1.8)
        ddx = local_x - nearest_x
        if math.hypot(ddx, local_z) < SpiderSilk.TRIGGER_DIST:
            self.triggered = True
            self.play_jumpscare()
            start_jumpscare(self)
            print('【盲蛛】嘶嘶——！你撞上了盲蛛的丝线！')

    def play_jumpscare(self):
        """蛛群突脸：瞬移到相机正前方，丝线隐藏、八只红眼骤然亮起放大"""
        cam = camera.world_position
        fwd = camera.forward
        self.position = Vec3(cam.x + fwd.x * SCARE_DIST, 0, cam.z + fwd.z * SCARE_DIST)
        self.rotation_y = math.degrees(math.atan2(cam.x - self.x, -(cam.z - self.z)))
        self.silk.enabled = False
        for eye in self.eyes:
            eye.enabled = True
            eye.scale = 0.22

    def reset(self):
        """扣命重生后复原丝线（不再重复触发同一根）——直接隐藏本体即可"""
        self.silk.enabled = False
        for eye in self.eyes:
            eye.enabled = False


class SpiderWeb(Entity):
    """★ 白丝陷阱（盲蛛重构版）：贴地半透明白丝（Y=0.05），宽度只占道路一半——
    绝不封死通道，玩家可以绕行。踩中：减速 60% × 3 秒 + 撕裂音 +
    4 根蛛腿从天花板（Y=4）极速扎落（纯心理压迫，不判定伤害）；
    随后白丝进入 5 秒失效期（半透明变灰），期间绝不重复触发减速。"""

    def __init__(self, position, rotation_y=0):
        super().__init__(
            model='quad', rotation_x=90, rotation_y=rotation_y,
            position=Vec3(position.x, position.y + 0.05, position.z),
            scale=(WEB_HALF_WIDTH, 2.2),        # 宽 1.5 米（半条路），长 2.2 米
            color=color.rgba(255, 255, 255, 100), double_sided=True,
        )
        self.is_dead = False
        self.initialized = True                 # ★ entity_gate 闸门
        self.cooldown = 0.0                     # 失效期倒计时
        self.base_color = color.rgba(255, 255, 255, 100)
        self.gray_color = color.rgba(150, 150, 155, 70)
        WEBS.append(self)

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):
            return
        if self.is_dead:
            return
        # ---- 失效期：变灰倒计时，结束后恢复半透明白 ----
        if self.cooldown > 0:
            self.cooldown -= time.dt
            if self.cooldown <= 0:
                self.cooldown = 0.0
                self.color = self.base_color
            return
        # ---- 踩中判定（仅同层：y 差 >1.2 米不算——如 2F / 地下室）----
        if player is None or player.is_dead or player.hidden:
            return
        if abs(player.y - self.y) > 1.2:
            return
        if dist_xz(player.position, self.position) < WEB_TRIGGER_DIST:
            self.trigger()

    def trigger(self):
        """踩中惩罚：减速 + 撕裂音 + 噪音（主怪回归预留接口）+ 蛛腿降临"""
        self.cooldown = WEB_COOLDOWN
        self.color = self.gray_color            # 失效期变灰
        if player is not None:
            player.web_slow_timer = WEB_SLOW_DURATION
        play_sfx('web_tear', volume=0.95)
        emit_noise(Vec3(self.x, 0, self.z), WEB_NOISE)   # 未来主怪可循声而来
        print('【白丝】噗嗤——黏丝缠住了你的脚踝！（移动速度大幅下降 3 秒！）')
        spawn_spider_legs(Vec3(self.x, 0, self.z))


def spawn_spider_legs(web_pos):
    """★ 盲蛛降临（规格）：陷阱正上方天花板（Y=4）瞬间生成 4 根白色细长蛛腿，
    animate_position 极速扎向玩家位置；落地停顿 0.5 秒后向上收回并销毁。
    不判定任何伤害——真正的威胁是 3 秒减速（深陷泥潭，极易被追上）。"""
    play_sfx('spider_hiss', volume=0.85)
    if player is not None:
        px, pz = player.x, player.z
    else:
        px, pz = web_pos.x, web_pos.z
    for ox, oz in ((0.5, 0.35), (-0.5, 0.35), (0.35, -0.5), (-0.35, -0.5)):
        tx, tz = px + ox, pz + oz
        home = Vec3(tx, 4.0 + SPIDER_LEG_LEN / 2, tz)       # 底端位于 Y=4 天花板
        leg = Entity(model='cube',
                     color=color.rgba(255, 255, 255, 225),
                     scale=(0.06, SPIDER_LEG_LEN, 0.06),
                     position=Vec3(home))
        leg.is_dead = False
        leg._home = home
        SPIDER_LEGS.append(leg)
        try:                                    # 极速下扎：0.12 秒插到地面
            leg.animate_position(Vec3(tx, SPIDER_LEG_LEN / 2 - 0.05, tz),
                                 duration=0.12, curve=curve.linear)
        except Exception:
            leg.position = Vec3(tx, SPIDER_LEG_LEN / 2 - 0.05, tz)
        invoke(_retract_spider_leg, leg, delay=0.12 + 0.5)  # 落地停顿 0.5 秒


def _retract_spider_leg(leg):
    """蛛腿落地停顿后向上收回（0.25 秒），随后销毁"""
    if leg is None or getattr(leg, 'is_dead', False):
        return
    try:
        leg.animate_position(Vec3(leg._home.x, leg._home.y, leg._home.z),
                             duration=0.25, curve=curve.linear)
    except Exception:
        pass
    invoke(_destroy_spider_leg, leg, delay=0.3)


def _destroy_spider_leg(leg):
    """安全销毁蛛腿（safe_destroy 语义：先摘链再销毁，绝不闪退）"""
    if leg is None or getattr(leg, 'is_dead', False):
        return
    leg.is_dead = True
    try:
        SPIDER_LEGS.remove(leg)
    except Exception:
        pass
    try:
        destroy(leg)
    except Exception:
        pass


class FakeSonar(Entity):
    """伪声呐（陷阱）：周期性发出冒充玩家的青色波纹与噪音，把怪物引向它
    （可能引开怪物，也可能把它引到你附近——双刃剑）。"""

    INTERVAL = (14.0, 22.0)    # 触发间隔随机区间
    NOISE_RADIUS = 25.0

    def __init__(self, position):
        super().__init__(position=position + Vec3(0, 0.6, 0))
        self.is_dead = False
        self.device = Entity(parent=self, model='cube', scale=(0.4, 0.5, 0.4),
                             color=color.rgb(45, 20, 20), y=0)
        self.lamp = Entity(parent=self, model='sphere', scale=0.12,
                           position=(0, 0.42, 0), color=color.rgb(255, 60, 60))
        self.timer = random.uniform(*FakeSonar.INTERVAL)
        self.pulse_t = random.uniform(0, math.tau)
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead:
            return
        # 待机：红灯缓慢呼吸
        self.pulse_t += time.dt
        b = 0.4 + 0.6 * abs(math.sin(self.pulse_t * 2.0))
        self.lamp.color = color.rgb(int(120 + 135 * b), 30, 30)
        # 周期触发：冒充玩家的波纹 + 噪音
        self.timer -= time.dt
        if self.timer <= 0:
            self.timer = random.uniform(*FakeSonar.INTERVAL)
            pos = Vec3(self.x, 0, self.z)
            RIPPLES.append(GroundRipple(pos))
            play_sfx('sonar', volume=0.4, pitch=random.uniform(0.8, 1.2))
            print('（远处传来一声陌生又熟悉的回声敲击……那不是你）')
            emit_noise(pos, FakeSonar.NOISE_RADIUS)


class Monster(Entity):
    """聆听者（主怪）：PATROL 巡逻 → CHASE 尖叫冲刺 → SEARCH 原地转圈 3 秒。
    优先加载 models/model_monster.obj；失败用组合人形（黑细身体+头+双臂+滴血红眼）。
    ★ 3D 音效：喘息/脚步尝试 Audio(is_3d=True) 并每帧更新位置；
    不支持时退化为距离音量（同样能听声辨位）。怪物只在地面层活动（y=0）。"""

    RADIUS = 0.6
    BODY_BASE_COLOR = color.rgb(10, 10, 12)

    def __init__(self, spawn_tile, world_pos=None):
        """spawn_tile：迷宫关的地块坐标；world_pos：硬编码关（L3）直接给世界坐标。"""
        if world_pos is not None:
            # ★ 规格二.3：采纳 world_pos.y——2F 出生怪（y 由解析斜坡 lerp 贴地）
            super().__init__(position=(world_pos.x, world_pos.y, world_pos.z))
            self.spawn_pos = Vec3(world_pos.x, world_pos.y, world_pos.z)
        else:
            world = level_manager.tile_to_world(spawn_tile)
            super().__init__(position=(world.x, 0, world.z))
            self.spawn_pos = Vec3(world.x, 0, world.z)
        self.is_dead = False
        self.spawn_tile = spawn_tile
        self.kind = 'listener'                  # ★ 生态分级标识（listener/crawler）
        self._base_scale = Vec3(1.0, 1.0, 1.0)  # ★ 原始比例（突脸放大后复位用）
        self._last_pos = Vec3(self.position)    # ★ 规格四：上帧位置（卡墙检测）
        self._slide_timer = 0.0                 # ★ 侧滑剩余时间
        self._slide_side = 1                    # ★ 侧滑方向
        self.state = 'PATROL'
        self.path = []
        self.noise_target = None
        self.patrol_target = None           # ★ 巡逻目标点（规格三）
        self.rest_timer = 0.0               # ★ 到达停歇计时（规格三）
        self.wander_timer = 0.0
        self.search_timer = 0.0
        self.cry_timer = 0.0
        self.breath_timer = random.uniform(0.5, 2.0)
        self.parts = []
        self._build_body()
        self.eye_l = Entity(parent=self, model='sphere', scale=0.09,
                            position=(-0.11, 2.72, -0.26),
                            color=color.rgb(255, 30, 30))
        self.eye_r = Entity(parent=self, model='sphere', scale=0.09,
                            position=(0.11, 2.72, -0.26),
                            color=color.rgb(255, 30, 30))
        add_box_collider(self, center=Vec3(0, 1.6, 0), size=Vec3(1.0, 3.2, 1.0))
        # ---- 3D 音效（每只独立）：喘息循环 + 脚步单次 ----
        self.breath_aud = load_3d_audio('mbreath', loop=True, volume=0.0)
        self.step_aud = load_3d_audio('monster_step', volume=0.5)
        self.step_timer = random.uniform(0.3, 1.0)
        try:
            if self.breath_aud is not None:
                self.breath_aud.play()
        except Exception:
            pass
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    def _build_body(self):
        self.body = None
        if MONSTER_OBJ_PATH:
            try:
                body = Entity(parent=self, model=MONSTER_OBJ_PATH,
                              color=self.BODY_BASE_COLOR)
                mn, mx = body.get_tight_bounds()
                size = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z, 0.001)
                body.scale = 3.2 / size
                body.y = 1.6 / body.scale_y
                self.body = body
                self.parts = [body]
                apply_lit_shader(body)
                return
            except Exception as _ex:
                if self.body is not None:
                    try:
                        destroy(self.body)
                    except Exception:
                        pass
                self.body = None
                # ★ 规格一.1：模型文件存在但解析失败 → 屏幕正中央红字警告
                try:
                    if model_warn_text is not None:
                        model_warn_text.enabled = True
                        print(f'\033[91m[警告] 怪物模型解析失败（{_ex}），'
                              f'已降级为红色方块\033[0m')
                except Exception:
                    pass
        # ★ 规格一.1：模型缺失时降级为红色方块（并在屏幕中央红字警告）
        _fallback_color = color.rgb(120, 25, 25)
        self.body = Entity(parent=self, model='cube', scale=(0.7, 2.6, 0.45),
                           y=1.3, color=_fallback_color)
        head = Entity(parent=self, model='cube', scale=(0.42, 0.4, 0.4),
                      position=(0, 2.72, -0.03), color=_fallback_color)
        arm_l = Entity(parent=self, model='cube', scale=(0.13, 1.5, 0.13),
                       position=(-0.48, 1.55, 0.0), rotation_z=0.10,
                       color=self.BODY_BASE_COLOR)
        arm_r = Entity(parent=self, model='cube', scale=(0.13, 1.5, 0.13),
                       position=(0.48, 1.55, 0.0), rotation_z=-0.10,
                       color=self.BODY_BASE_COLOR)
        self.parts = [self.body, head, arm_l, arm_r]
        for p in self.parts:
            apply_lit_shader(p)

    # ---------------- 3D 音效更新（每帧）----------------
    @staticmethod
    def _dist_volume(d):
        """★ 规格一.2（手动线性衰减，替代 3D 引擎）：>20 米静音；
        <20 米音量 = 1.0 - distance/20（越近越大，贴身 1.0）。"""
        if d > 20.0:
            return 0.0
        return max(0.0, 1.0 - d / 20.0)

    def _update_audio(self, dt):
        """★ 规格一：每帧强制 sound.position = self.position + 距离音量曲线。
        喘息（循环）与脚步（单次）均以 load_3d_audio 初始化（is_3d=True，
        引擎不支持时自动退化——由本距离曲线模拟听声辨位）。"""
        if player is None:
            return
        d = dist_xz(self.position, player.position)
        k = self._dist_volume(d)
        set_audio_position(self.breath_aud, self.position)   # 每帧位置更新
        try:
            if self.breath_aud is not None:
                self.breath_aud.volume = 0.55 * k * (0.6 if active_modifier
                                                     and active_modifier.get('quiet') else 1.0)
        except Exception:
            pass
        if k > 0.0 and d < MONSTER_AUDIO_RANGE:
            self.step_timer -= dt
            if self.step_timer <= 0:
                self.step_timer = 0.7 - 0.32 * (1 - d / MONSTER_AUDIO_RANGE)
                set_audio_position(self.step_aud, self.position)
                try:
                    if self.step_aud is not None:
                        self.step_aud.volume = max(0.25, k)   # 近处满响、远处随曲线衰减
                        self.step_aud.play()
                    else:
                        play_sfx('monster_step', volume=max(0.25, k))
                except Exception:
                    play_sfx('monster_step', volume=max(0.25, k))

    # ---------------- 回声高亮 ----------------
    def reveal(self):
        if self.is_dead:
            return
        _register_echo_reveal(self, rgb=(255, 0, 0))   # ★ 规格二.5：怪物纯红线框

    # ---------------- 状态复位 ----------------
    def reset(self):
        """回到出生点，恢复巡逻状态与原始模型外观（兼容 L3 无网格关）"""
        if self.spawn_tile is not None:
            w = level_manager.tile_to_world(self.spawn_tile)
            self.spawn_pos = Vec3(w.x, 0, w.z)
        self.position = Vec3(self.spawn_pos.x, self.spawn_pos.y, self.spawn_pos.z)
        self.scale = Vec3(self._base_scale)   # ★ 撤销突脸放大（保持爬行怪原比例）
        self.state = 'PATROL'
        self.path = []
        self.wander_timer = 0.0
        self.search_timer = 0.0
        for p in self.parts:
            p.color = self.BODY_BASE_COLOR
            apply_lit_shader(p)
            set_wireframe(p, False)
        for eye in (self.eye_l, self.eye_r):
            eye.y = 2.72
            eye.scale = 0.09
            eye.color = color.rgb(255, 30, 30)

    # ---------------- 突脸 ----------------
    def play_jumpscare(self):
        cam = camera.world_position
        fwd = camera.forward
        tx = cam.x + fwd.x * SCARE_DIST
        tz = cam.z + fwd.z * SCARE_DIST
        self.position = Vec3(tx, 0, tz)
        self.rotation_y = math.degrees(math.atan2(cam.x - tx, -(cam.z - tz)))
        self.state = 'SCARE'
        for eye in (self.eye_l, self.eye_r):
            eye.y = 1.9
            eye.scale = 0.45
            eye.color = color.rgb(255, 20, 20)
        # ★ 规格一.3：突脸瞬间整体放大 2 倍（贴脸压迫感；reset 恢复原始比例）
        self.scale = Vec3(self.scale_x * 2, self.scale_y * 2, self.scale_z * 2)
        for p in self.parts:
            p.color = color.rgb(20, 0, 0)

    # ---------------- 感知 ----------------
    def hear_noise(self, position, radius):
        """★ 规格四：分级噪音感应（dist_xz 判定天然无视楼层 Y——
        楼上敲击楼下能听见；半径 ≥50 视为全图事件）。"""
        if self.is_dead or game_state != GameState.PLAYING or scare_active:
            return
        # ★ 规格四.2：半径 ≥50 视为全图事件（120 米地图上 50 米不足以跨图，
        #   按规格意图落地/撞门类巨响让所有怪物立刻 CHASE）
        if radius < 50.0 and dist_xz(self.position, position) > radius:
            return
        lm = level_manager
        if lm.grid:
            # ---- 迷宫关（L1/L2）：BFS 精确寻路 ----
            goal = lm.nearest_floor_tile(position)
            self.noise_target = lm.tile_to_world(goal)
            cells = lm.bfs_path(lm.world_to_tile(self.position), goal)
            self.path = ([lm.tile_to_world(t) for t in cells]
                         if cells else [self.noise_target])
        else:
            # ---- ★ 硬编码关（L3 实验室）：无网格，直线冲向声源（碰撞解算防穿墙）----
            self.noise_target = Vec3(position.x, 0, position.z)
            self.path = [Vec3(self.noise_target.x, 0, self.noise_target.z)]
        if self.state != 'CHASE':
            self.state = 'CHASE'
            self.cry_timer = 1.5
            play_sfx('roar', volume=0.9)
            play_sfx('monster_scream', volume=1.0)   # ★ 规格四.1：发现瞬间尖叫
            fear_value[0] = 100.0                    # ★ 恐怖值拉满（触发心跳）
            print('【聆听者嘶吼】呃 啊 啊 啊——！！它扑向了声源！')

    # ---------------- 行为 ----------------
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
        # ★ 规格一.1：前方 1 米射线探墙——受阻则向侧方偏移（Flanking 绕障；
        # 台阶标记 is_stair_step 不算障碍，保证怪物照常上下楼）
        move_ang = math.atan2(dz, dx)
        try:
            hit = raycast(Vec3(self.x, 1.2, self.z),
                          Vec3(math.cos(move_ang), 0, math.sin(move_ang)),
                          distance=1.0, ignore=(self,))
            blocked = (hit is not None and hit.entity is not None
                       and getattr(hit.entity, 'is_terrain', False)
                       and not getattr(hit.entity, 'is_stair_step', False))
        except Exception:
            blocked = False
        if blocked:
            # ★ 规格四：贴墙滑行——按 45°/90°/135° 阶梯探测侧向路点，
            # 全被堵（死角）则短暂倒退脱困，绝不原地贴墙抖动
            self._flank_timer = 0.45
            _cur = getattr(self, '_flank_dir', 1)
            picked = None
            for _ang in (45, 90, 135):
                for side in (_cur, -_cur):
                    a2 = move_ang + side * math.radians(_ang)
                    try:
                        h2 = raycast(Vec3(self.x, 1.2, self.z),
                                     Vec3(math.cos(a2), 0, math.sin(a2)),
                                     distance=1.0, ignore=(self,))
                        free = not (h2 is not None and h2.entity is not None
                                    and getattr(h2.entity, 'is_terrain', False)
                                    and not getattr(h2.entity, 'is_stair_step', False))
                        if free:
                            picked = side * _ang
                            self._flank_dir = side
                            break
                    except Exception:
                        pass
                if picked is not None:
                    break
            self._flank_off = picked if picked is not None else 180.0  # 死角→倒退
        if getattr(self, '_flank_timer', 0) > 0:
            self._flank_timer -= time.dt
            move_ang += math.radians(getattr(self, '_flank_off', 60.0))
        step = min(speed * time.dt, d)
        self.x += math.cos(move_ang) * step
        self.z += math.sin(move_ang) * step
        self.rotation_y = math.degrees(math.atan2(dx, -dz))
        resolve_collisions(self, self.RADIUS)
        resolve_door_collision(self)            # ★ 关闭的门阻挡怪物（第三关）
        push_out_if_stuck(self)
        return False

    def _pick_patrol_destination(self):
        """★ 规格三：全图随机巡逻——废弃原地打转，从全图合法点中
        random.choice() 选定 patrol_target，寻路走向该点；到达后停歇 2 秒。"""
        lm = level_manager
        if not lm.grid:
            # ---- 硬编码关（L3）：全图开阔点随机选点 ----
            goal = random.choice(lm.open_points) if lm.open_points \
                else Vec3(0, 0, 0)
            self.patrol_target = Vec3(goal.x, 0, goal.z)
            self.path = [Vec3(goal.x, 0, goal.z)]
        else:
            # ---- 迷宫关（L1/L2）：全图地板格随机选点 + BFS 寻路 ----
            tiles = lm.floor_tiles if lm.floor_tiles else []
            goal = random.choice(tiles) if tiles else lm.random_floor_tile()
            self.patrol_target = lm.tile_to_world(goal)
            cells = lm.bfs_path(lm.world_to_tile(self.position), goal)
            self.path = ([lm.tile_to_world(t) for t in cells]
                         if cells else [self.patrol_target])
    def _nearest_stair(self):
        """★ 规格二.2：最近的上行楼梯（连接 1F↔2F 的 RAMPS）"""
        best, bd = None, 1e18
        for r in list(RAMPS):
            if getattr(r, 'is_dead', False) or r.rise <= 0:
                continue
            d = dist_xz(self.position, r.position)
            if d < bd:
                bd, best = d, r
        return best

    def _route_to(self, world_pos):
        """★ 通用寻路：网格关 BFS / 硬编码关直线（跨层追击复用）"""
        lm = level_manager
        if lm.grid:
            goal = lm.nearest_floor_tile(world_pos)
            cells = lm.bfs_path(lm.world_to_tile(self.position), goal)
            self.path = ([lm.tile_to_world(t) for t in cells]
                         if cells else [lm.tile_to_world(goal)])
        else:
            self.path = [Vec3(world_pos.x, 0, world_pos.z)]

    # ---------------- 每帧逻辑 ----------------
    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead or player is None or scare_active:
            return
        dt = time.dt
        self._update_audio(dt)
        # ★ 多层 y 适配：怪物沿楼梯/平台平滑升降（与玩家相同的 lerp 逻辑）
        _ty = get_ground_height(self.x, self.z, self.y)
        self.y = lerp(self.y, _ty, min(time.dt * GROUND_LERP_SPEED, 1.0))
        spd_mult = active_modifier.get('monster_speed', 1.0) if active_modifier else 1.0

        # ---- ★ 规格四：位移检测防卡墙——移动状态下本帧位移几乎为 0
        #      → 立即触发侧滑（垂直于目标方向的平移向量，强行绕过阻挡）----
        _moving = self.state in ('PATROL', 'CHASE') and bool(self.path)
        if _moving and self._slide_timer <= 0:
            if dist_xz(self.position, self._last_pos) < 0.005:
                self._slide_timer = 0.35
                self._slide_side = 1 if getattr(self, '_flank_dir', 1) > 0 else -1
        if self._slide_timer > 0 and self.path:
            self._slide_timer -= dt
            tgt = self.path[0]
            dx, dz = tgt.x - self.x, tgt.z - self.z
            d = math.hypot(dx, dz) or 1.0
            side_x = -dz / d * self._slide_side     # 垂直方向单位向量
            side_z = dx / d * self._slide_side
            _ss = MONSTER_PATROL_SPEED * dt
            self.x += side_x * _ss
            self.z += side_z * _ss
        self._last_pos = Vec3(self.position)

        if self.state == 'PATROL':
            had_path = bool(self.path)
            arrived = self._follow_path(MONSTER_PATROL_SPEED * spd_mult
                                        * (0.6 if self.kind == 'crawler' else 1.0))
            self.wander_timer -= dt
            if arrived and had_path:
                # ★ 规格三：真正走到巡逻目标 → 原地停歇 2 秒再选下一个点
                self.state = 'PATROL_REST'
                self.rest_timer = 2.0
            elif arrived or self.wander_timer <= 0:
                # 首次无路径/超时 → 全图随机选点
                self._pick_patrol_destination()

        elif self.state == 'PATROL_REST':
            self.rest_timer -= dt
            if self.rest_timer <= 0:
                self._pick_patrol_destination()
                self.state = 'PATROL'

        elif self.state == 'CHASE':
            self.cry_timer -= dt
            if self.cry_timer <= 0:
                self.cry_timer = 1.5
                d = dist_xz(self.position, player.position)
                print(f'【聆听者】沉重的疾行声……（距离约 {d:.1f} 米）')
            _spd = MONSTER_CHASE_SPEED * spd_mult \
                * (0.5 if self.kind == 'crawler' else 1.0)
            if abs(player.y - self.y) > 2.0:
                # ★ 规格二.2：跨层追击——与玩家不在同一层时先走向最近的上行
                # 楼梯；踏坡期间 Y 由解析斜坡 + lerp 平滑过渡（绝不瞬移/穿模）
                r = self._nearest_stair()
                if r is not None:
                    if dist_xz(self.position, r.position) > 1.5:
                        self._route_to(Vec3(r.x, 0, r.z))
                        self._follow_path(_spd)
                    else:
                        # 已在楼梯脚：直接沿坡冲向楼梯顶端
                        self.path = [Vec3(r.x + r.ax * r.run, 0,
                                          r.z + r.az * r.run)]
                        self._follow_path(_spd)
                    arrived = False               # 跨层途中不算到达声源
                else:
                    arrived = self._follow_path(_spd)
            else:
                arrived = self._follow_path(_spd)
            if arrived:
                self.state = 'SEARCH'
                self.search_timer = 3.0
                print('【聆听者】嘶……嘶……（它到达声源，原地搜寻）')

        elif self.state == 'SEARCH':
            self.rotation_y += 120 * dt
            self.search_timer -= dt
            if self.search_timer <= 0:
                self.state = 'PATROL'
                self._pick_patrol_destination()   # ★ 全图随机选点（不回出生点）
                print('【聆听者】一无所获……它退回黑暗深处')

        # ---- 致杀判定（规格一.1）：三维距离 < 1.5 米必触发突脸。
        # 三维判定消除"楼梯中途 y-lerp 未跟上导致贴身不判定"的漏洞；
        # 藏进柜子（hidden）仍豁免——那是核心潜行机制。----
        if not getattr(player, 'is_dead', False) and not player.hidden:
            if distance(self.position, player.position) < 1.5:
                start_jumpscare(self)


def _delayed_monster_restore(monster):
    if monster is None or getattr(monster, 'is_dead', False):
        return
    for p in monster.parts:
        p.color = Monster.BODY_BASE_COLOR
        apply_lit_shader(p)
        set_wireframe(p, False)


class Player(Entity):
    """盲女伊芙琳：3 条命（可觉醒+1），随身微光点光源与手部实体。
    潜行(左键按住)+屏息(Q 事件驱动)零噪音；右键回声；F 投掷（有管子优先）；
    E 交互（日记/保险丝/柜子/管子）；★ 楼梯/平台高度平滑插值；
    ★ 柜内透孔窥视（摄像机前推 + 窥视遮罩）。死亡复活保留日记与保险丝。"""

    PLAYER_RADIUS = 0.5
    MOUSE_SENSITIVITY = 40.0

    def __init__(self, position, yaw=0):
        super().__init__(position=position, rotation_y=yaw)
        self.is_dead = False
        self.stamina = BASE_MAX_STAMINA
        self.oxygen = O2_MAX                    # 氧气（屏息消耗）
        self.is_holding_breath = False          # ★ 屏息状态（input 事件驱动，规格字段名）
        self.o2_exhaust = 0.0                   # 屏息疲惫期剩余时间
        self._shake_t = 0.0                     # ★ 镜头晃动剩余时间
        self._stamina_out = False               # ★ 体力力竭边沿检测
        self.sneak_breath_timer = 0.0           # 潜行呼吸噪音节拍
        self.echo_cooldown = 0.0
        self.stone_cooldown = 0.0
        self.step_accum = 0.0
        self.has_pipe = False                   # 是否持有空管子（F 优先投掷）
        self.has_keycard = False                # ★ 第三关：红色门禁卡
        self.web_slow_timer = 0.0               # ★ 白丝缠足减速剩余时间（秒）
        self.on_blood = False                   # ★ 第三关：是否踩在血迹上（减速 50%）
        self.hidden = False                     # 藏在柜子里（怪物无法发现）
        self.hidden_cabinet = None              # 当前藏身的柜子
        self.spawn_position = Vec3(position.x, 0, position.z)   # 出生点（含高度）
        self._base_h = STAND_HEIGHT
        self.camera_pivot = Entity(parent=self, y=STAND_HEIGHT)
        camera.parent = self.camera_pivot
        camera.position = Vec3(0, 0, 0)
        camera.rotation = Vec3(0, 0, 0)
        camera.fov = 90
        add_box_collider(self, center=Vec3(0, 1.0, 0), size=Vec3(0.9, 1.9, 0.9))
        # ★ 微光视野：摄像机随身点光源
        self.player_light = None
        try:
            light_dist = 1.5 if (active_modifier and active_modifier.get('vision_blur')) \
                else 3.0                        # ★ 规格二.2：距离=3——2~3 米内才隐约见墙轮廓
            self.player_light = PointLight(parent=camera,
                                           color=color.rgba(30, 30, 35, 255),   # 微弱冷光
                                           distance=light_dist, shadows=False)
            self.player_light_distance = light_dist   # ★ 测试断言用
        except Exception:
            self.player_light = None
        # ★ 手部反馈：右下角的手（伊芙琳的探路之手），右键敲击时快速下挥
        self.hand = Entity(parent=self.camera_pivot, model='cube',
                           scale=(0.10, 0.26, 0.30),
                           position=(0.34, -0.36, -0.52),
                           rotation=(-12, 8, 6),
                           color=color.rgb(208, 188, 168))
        self.hand_base = Vec3(0.34, -0.36, -0.52)
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）

    # ---------------- ★ 屏息系统（事件驱动 + 氧气消耗 + UI）----------------
    def _fail_breath(self):
        """氧气耗尽：强制结束屏息，沉重喘息 = 巨大噪音 + 10 秒疲惫期"""
        self.is_holding_breath = False
        self.o2_exhaust = BREATH_EXHAUST
        _exhaust_pulse[0] = 1.0                 # ★ 规格四.2：缺氧力竭红屏脉冲
        play_sfx('gasp', volume=1.0)
        emit_noise(self.position, GASP_NOISE)
        print('【屏息失败】哈啊——！！你憋不住了，巨大的喘息声暴露了位置！')

    def _update_breath(self, dt):
        """★ 屏息核心逻辑（柜内外通用）：
        Q 由 input() 事件驱动 is_holding_breath（'q' 按下 / 'q up' 松开）；
        屏息时每秒耗氧 25 点且完全静音（连呼吸循环音都消失）；
        非屏息时氧气缓慢恢复。★ UI：蓝色氧气条仅在屏息时显示。"""
        if self.o2_exhaust > 0:
            self.o2_exhaust = max(0.0, self.o2_exhaust - dt)   # 疲惫期倒计时
            self.is_holding_breath = False
        elif self.is_holding_breath:
            if self.oxygen > 0:
                self.oxygen = max(0.0, self.oxygen - O2_DRAIN * dt)
                try:
                    if breath_audio is not None:
                        breath_audio.volume = 0.0    # 屏息：连呼吸声都消失
                except Exception:
                    pass
                if self.oxygen <= 0:
                    self._fail_breath()
            else:
                self._fail_breath()
        else:
            self.oxygen = min(O2_MAX, self.oxygen + O2_REGEN * dt)
            try:
                if breath_audio is not None:
                    breath_audio.volume = 0.35
            except Exception:
                pass
        # ---- ★ UI：蓝色氧气条（宽度绑定 oxygen），仅屏息时显示 ----
        show = self.is_holding_breath
        o2_bg.enabled = show
        o2_fill.enabled = show
        o2_label.enabled = show
        if show:
            o2_fill.scale = Vec3(0.62 * self.oxygen / O2_MAX, 0.022, 1)
            o2_fill.color = color.rgb(90, 170, 255)

    # ---------------- 回声敲击（含手部动画）----------------
    def try_echo(self):
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        if self.hidden:
            return
        if self.echo_cooldown > 0:
            return
        if self.stamina < ECHO_STAMINA_COST:
            print('【回声】体力不足，无法凝聚听觉（需要 10 点体力）')
            return
        self.stamina -= ECHO_STAMINA_COST
        self.echo_cooldown = get_echo_cooldown()
        origin = Vec3(self.position.x, self.position.y, self.position.z)
        ECHO_SPHERES.append(EchoSphere(origin + Vec3(0, 1.0, 0)))
        RIPPLES.append(GroundRipple(origin))
        invoke(spawn_delayed_ripple, Vec3(origin.x, origin.y, origin.z), delay=0.3)
        play_sfx('sonar')
        self._animate_hand()                    # ★ 手部下砸动画
        refresh_minimap()
        emit_noise(self.position, ECHO_NOISE_RADIUS)   # ★ 规格触发噪音：半径 15

    def _animate_hand(self):
        """★ 手部反馈：敲击时手快速下砸再收回（animate_position + 延迟回位）"""
        if self.hand is None:
            return
        try:
            self.hand.animate_position(
                self.hand_base + Vec3(0.02, -0.16, 0.06), duration=0.09,
                curve=curve.out_expo)
            invoke(self._hand_back, delay=0.12)
        except Exception:
            pass

    def _hand_back(self):
        if self.hand is not None and not self.is_dead:
            try:
                self.hand.animate_position(self.hand_base, duration=0.16,
                                           curve=curve.out_expo)
            except Exception:
                pass

    # ---------------- 投掷（有管子优先）----------------
    def throw_item(self):
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        if self.hidden:
            return
        if self.stone_cooldown > 0:
            return
        self.stone_cooldown = STONE_COOLDOWN
        d = camera.forward
        stone = Stone(camera.world_position + Vec3(0, 0.1, 0), d, pipe=self.has_pipe)
        STONES.append(stone)
        if self.has_pipe:
            self.has_pipe = False
            print('（嗖——金属管脱手飞出，将在落点制造连环假回声！）')
        else:
            print('（嗖——石头脱手飞出）')

    # ---------------- 交互（E）：柜子 > 日记 > 管子 > 保险丝 ----------------
    def try_interact(self):
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        global collected_fuses, collected_diaries, diary_open
        # ---- 藏在柜子里：E 离开 ----
        if self.hidden:
            self.hidden = False
            self.hidden_cabinet = None
            set_peek_mask(False)                # 撤掉柜内窥视遮罩
            print('（你推开柜门，重新潜入黑暗）')
            return
        if diary_open:                          # 阅读中：E 合上日记（input 已优先处理）
            return
        # ---- 找最近的可交互目标（含高度判定：隔着楼层不交互）----
        best, best_d, best_kind = None, 2.0, None
        for c in list(CABINETS):
            if c.is_dead or abs(self.y - c.y) > 2.2:
                continue
            d = dist_xz(self.position, c.position)
            if d < best_d:
                best, best_d, best_kind = c, d, 'cabinet'
        for b in list(DIARIES):
            if b.is_dead or abs(self.y - b.y) > 2.2:
                continue
            d = dist_xz(self.position, b.position)
            if d < best_d:
                best, best_d, best_kind = b, d, 'diary'
        for p in list(PIPES):
            if p.is_dead or abs(self.y - p.y) > 2.2:
                continue
            d = dist_xz(self.position, p.position)
            if d < best_d:
                best, best_d, best_kind = p, d, 'pipe'
        for f in list(FUSES):
            if f.is_dead or abs(self.y - f.y) > 2.2:
                continue
            d = dist_xz(self.position, f.position)
            if d < best_d:
                best, best_d, best_kind = f, d, 'fuse'
        # ---- ★ 第三关交互物：推拉门 / 残缺报告 / 门禁卡 / 手术台 / 主控门 ----
        for d in list(DOORS):
            if d.is_dead or abs(self.y - d.y) > 2.2:
                continue                    # ★ 开着的门也参与交互（可手动关门）
            dd = dist_xz(self.position, d.position)
            if dd < best_d:
                best, best_d, best_kind = d, dd, 'door'
        for rp in list(REPORTS):
            if rp.is_dead or abs(self.y - rp.y) > 2.2:
                continue
            dd = dist_xz(self.position, rp.position)
            if dd < best_d:
                best, best_d, best_kind = rp, dd, 'report'
        for kc in list(KEYCARDS):
            if kc.is_dead or abs(self.y - kc.y) > 2.2:
                continue
            dd = dist_xz(self.position, kc.position)
            if dd < best_d:
                best, best_d, best_kind = kc, dd, 'keycard'
        for tb in list(TABLES):
            if tb.is_dead or tb.searched or abs(self.y - tb.y) > 2.2:
                continue
            dd = dist_xz(self.position, tb.position)
            if dd < best_d:
                best, best_d, best_kind = tb, dd, 'table'
        for tk in list(TANKS):                   # ★ 规格三：培养罐可搜查
            if tk.is_dead or tk.searched or abs(self.y - tk.y) > 2.2:
                continue
            dd = dist_xz(self.position, tk.position)
            if dd < best_d and dd < 2.2:
                best, best_d, best_kind = tk, dd, 'tank'
        for dr in list(DRAWERS):
            if dr.is_dead or dr.searched or abs(self.y - dr.y) > 2.2:
                continue
            dd = dist_xz(self.position, dr.position)
            if dd < best_d:
                best, best_d, best_kind = dr, dd, 'drawer'
        for md in list(MAIN_DOORS):
            if md.is_dead or abs(self.y - md.y) > 2.2:
                continue
            dd = dist_xz(self.position, md.position)
            if dd < 3.2 and (best is None or dd < best_d):   # ★ 规格三.3：距离放宽 3.2 米
                best, best_d, best_kind = md, dd, 'maindoor'
        if best is None:
            return
        if best_kind == 'cabinet':
            # ★ 钻入柜子：碰撞体留在柜内；面向柜门方向；摄像机将前推到门缝处
            self.hidden = True
            self.hidden_cabinet = best
            self.position = Vec3(best.x, self.y, best.z)
            self.rotation_y = best.door_yaw     # 面向柜门（往外看的方向）
            self.is_holding_breath = False      # 进柜时松开屏息（柜内由遮罩呈现）
            set_peek_mask(True)                 # ★ 柜内窥视遮罩（四周黑、中间竖缝）
            play_sfx('skill', volume=0.3)
            print('（你屏住呼吸钻进储物柜，眼睛贴上门缝往外看……按 E 离开）')
        elif best_kind == 'diary':
            open_diary(best.text)       # ★ E 仅阅读（不销毁——R 才拾取）
        elif best_kind == 'report':
            open_diary(best.text)       # ★ E 仅阅读（不销毁——R 才拾取）
        elif best_kind == 'pipe':
            safe_destroy(best)
            self.has_pipe = True
            print('【管子】你拾起一根空金属管（按 F 投掷：更大噪音 + 多次假回声）')
        elif best_kind == 'fuse':
            safe_destroy(best)
            collected_fuses += 1
            update_status_text()
            print('【保险丝】咔哒——你拔下一枚微光保险丝')
            if collected_fuses >= FUSES_NEEDED:
                for gate in list(level_manager.exit_gates):
                    if gate is not None and not gate.is_dead:
                        gate.unlock()
                print('【出口】保险丝集齐——出口的绿灯亮起了！')
        elif best_kind == 'door':
            if best.open:
                best.close()                    # ★ 手动关门（播放 sfx_door_close）
            else:
                best.silent_open()              # ★ 静音开门（播放 sfx_door_open，零噪音）
        elif best_kind == 'report':
            open_diary(best.text)       # ★ E 仅阅读（不销毁——R 才拾取）
        elif best_kind == 'keycard':
            safe_destroy(best)
            self.has_keycard = True
            update_status_text()
            play_sfx('skill', volume=0.5)
            print('【门禁卡】你拿到了一张红色门禁卡——主控门可以刷开了')
        elif best_kind == 'table':
            best.search()                       # ★ 搜查手术台（30% 掉落）
        elif best_kind == 'tank':
            best.search()                       # ★ 搜查培养罐（30% 掉落）
        elif best_kind == 'drawer':
            best.search()                       # ★ 搜查抽屉柜（概率产出）
        elif best_kind == 'maindoor':
            if self.has_keycard:
                win_game()                      # ★ 携带门禁卡按 E → 触发 WIN
            else:
                print('【主控门】刷卡器红光一闪——需要一张红色门禁卡')

    def try_pickup_readable(self):
        """★ R 键拾取：销毁附近的日记/报告实体并记录到已收集列表。
        与 E 键阅读分离——阅读不会销毁实体，拾取才会。"""
        global current_round_fragments
        if game_state != GameState.PLAYING or self.is_dead or scare_active:
            return
        global collected_diaries
        best, best_d = None, 2.0
        for d in list(DIARIES):
            if d.is_dead or abs(self.y - d.y) > 2.2:
                continue
            dd = dist_xz(self.position, d.position)
            if dd < best_d:
                best, best_d = d, dd
        for rp in list(REPORTS):
            if rp.is_dead or abs(self.y - rp.y) > 2.2:
                continue
            dd = dist_xz(self.position, rp.position)
            if dd < best_d:
                best, best_d = rp, dd
        if best is None:
            return
        # ★ 规格二.2：单局上限 8 个——超限禁止拾取
        if current_round_fragments >= 8:
            show_toast('本局已无法拾取更多碎片')
            return
        safe_destroy(best)
        if isinstance(best, Diary):
            collected_diaries += 1
        current_round_fragments += 1
        # ★ 规格一.3：碎片 ID 写入 save_data.json（跨局持久化）
        fid = getattr(best, 'frag_id', None)
        if fid is not None and fid not in collected_fragment_ids:
            collected_fragment_ids.append(fid)
        save_fragment_data()
        _unlock = min(10, len(collected_fragment_ids) // 10)
        show_toast(f'碎片 {len(collected_fragment_ids)}/50 · '
                   f'记忆解锁 {_unlock}/10 · {best.text[:16]}')
        play_sfx('skill', volume=0.4)
        update_status_text()
        print(f'【拾取】碎片入袋（本局 {current_round_fragments}/8）——{best.text}')

    # ---------------- 扣命重生 ----------------
    def respawn(self):
        self.position = Vec3(self.spawn_position.x, self.spawn_position.y,
                             self.spawn_position.z)
        self.stamina = BASE_MAX_STAMINA
        self.oxygen = O2_MAX
        self.is_holding_breath = False
        self.o2_exhaust = 0.0
        self._shake_t = 0.0
        self._stamina_out = False
        self.web_slow_timer = 0.0               # ★ 重生解除白丝减速
        self.echo_cooldown = 0.0
        self.stone_cooldown = 0.0
        self.hidden = False
        self.hidden_cabinet = None
        set_peek_mask(False)
        self._base_h = STAND_HEIGHT
        self.camera_pivot.x = 0.0
        self.camera_pivot.y = STAND_HEIGHT
        self.camera_pivot.z = 0.0              # 复位柜内窥视前推
        self.camera_pivot.rotation_x = 0.0

    # ---------------- 每帧逻辑 ----------------
    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self):           # ★ 防闪退闸门：initialized + PLAYING（规格）
            return
        if self.is_dead or scare_active:
            return
        dt = time.dt

        # ---- ★ 白丝缠足倒计时（盲蛛重构：踩中后 3 秒）----
        if self.web_slow_timer > 0:
            self.web_slow_timer -= dt

        # ---- ★ 屏息/氧气（柜内外通用，事件驱动）----
        self._update_breath(dt)

        # ---- 藏在柜子里：透孔窥视 + 冻结移动（心跳与外界声音继续）----
        if self.hidden:
            # ★ 规格三：柜内允许鼠标左右看（yaw），但限制在柜门朝向 ±45°
            #   防止转到背面穿模看到柜外；俯仰保持冻结（门缝视角）
            if self.hidden_cabinet is not None:
                _base_yaw = self.hidden_cabinet.door_yaw
                sens = SAVE['settings']['sensitivity']
                self.rotation_y += mouse.velocity[0] * sens
                _rel = (self.rotation_y - _base_yaw + 180) % 360 - 180
                if _rel > 45:
                    self.rotation_y = _base_yaw + 45
                elif _rel < -45:
                    self.rotation_y = _base_yaw - 45
            # ★ 摄像机向柜门方向平滑前推（本地 -z 为面前），卡在门缝处往外看
            self.camera_pivot.z = lerp(self.camera_pivot.z, CAM_PEEK_Z,
                                       min(dt * 10.0, 1.0))
            return
        # 离开柜子后：摄像机平滑退回原位
        self.camera_pivot.z = lerp(self.camera_pivot.z, 0.0, min(dt * 10.0, 1.0))

        # ---- 冷却推进 ----
        self.echo_cooldown = max(0.0, self.echo_cooldown - dt)
        self.stone_cooldown = max(0.0, self.stone_cooldown - dt)

        # ---- 视角（X 轴限制 -80~80）----
        sens = SAVE['settings']['sensitivity']
        self.rotation_y += mouse.velocity[0] * sens
        self.camera_pivot.rotation_x = clamp(
            self.camera_pivot.rotation_x - mouse.velocity[1] * sens, -80, 80)

        # ---- 输入意图：左键按住 = 潜行；Shift = 奔跑 ----
        sneaking = held_keys['left mouse'] == 1
        want_run = (held_keys['left shift'] or held_keys['right shift']) and not sneaking
        ix = held_keys['d'] - held_keys['a']
        iz = held_keys['s'] - held_keys['w']
        moving = ix != 0 or iz != 0

        # ---- 体力 ----
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
        # ★ 规格四.2：体力/氧气耗尽瞬间 → 屏幕泛红脉冲（力竭反馈）
        if self.stamina <= 0 and not self._stamina_out:
            self._stamina_out = True
            _exhaust_pulse[0] = 1.0
        elif self.stamina > 5.0:
            self._stamina_out = False

        # ---- 移动三态 ----
        if sneaking:
            speed, mode = WALK_SPEED * SNEAK_MULT, 'sneak'
        elif running:
            speed, mode = WALK_SPEED * RUN_MULT, 'run'
        else:
            speed, mode = WALK_SPEED, 'walk'

        # ---- ★ 第三关：踩到血迹 → 移动速度乘数强制 0.5（规格）----
        self.on_blood = False
        for bp in list(BLOODPOOLS):
            if bp.is_dead:
                continue
            if abs(self.y - bp.y) > 2.2:
                continue                            # ★ 同层判定：地下室的血不减速地面
            if dist_xz(self.position, bp.position) < 1.0:   # 规格：距离 < 1
                self.on_blood = True
                break
        if self.on_blood:
            speed *= 0.5

        # ---- ★ 白丝缠足（盲蛛重构）：踩中白丝后 3 秒内速度降低 60% ----
        if self.web_slow_timer > 0:
            speed *= WEB_SLOW_MULT

        if moving:
            direction = (self.forward * (-iz) + self.right * ix).normalized()
            self.position += direction * speed * dt
            resolve_collisions(self, self.PLAYER_RADIUS)
            resolve_collisions(self, self.PLAYER_RADIUS)   # ★ 规格一.3：二次解算防墙角挤入
            push_out_if_stuck(self)
            resolve_door_collision(self)        # ★ 关闭的门阻挡通行（第三关）
            # ---- ★ 第三关：奔跑速度 > 8 撞向关闭的门 → 暴力撞开（巨大噪音）----
            if running and speed > 8.0:
                for d in list(DOORS):
                    if not d.is_dead and not d.open \
                            and dist_xz(self.position, d.position) < 1.1:
                        d.bash_open()
                        self._shake_t = 0.35    # ★ 规格三.3：暴力撞门的镜头晃动
            silent_walk = walk_is_silent()      # 觉醒·静音鞋
            if mode != 'sneak' and not silent_walk:
                self.step_accum += speed * dt
                step_len = 2.2 if mode == 'walk' else 2.6
                if self.step_accum >= step_len:
                    self.step_accum = 0.0
                    if self.on_blood:
                        # ★ 血迹上的黏腻脚步声（噪音按当前移动档位计算）
                        emit_noise(self.position,
                                   RUN_NOISE if mode == 'run' else WALK_NOISE)
                        play_sfx('squish', volume=0.55,
                                 pitch=random.uniform(0.85, 1.1))
                    elif mode == 'run':
                        emit_noise(self.position, RUN_NOISE)
                        play_sfx('step_run', volume=0.9,
                                 pitch=random.uniform(0.9, 1.1))
                    else:
                        emit_noise(self.position, WALK_NOISE)
                        play_sfx('step', volume=0.6,
                                 pitch=random.uniform(0.85, 1.15))

        # ---- ★ 楼梯与地形高度平滑适配（"楼梯走不了"修复核心）----
        # 射线检测脚下 2 米内的地形（地面/台阶/平台的 BoxCollider 顶面），
        # y 坐标用插值平滑上升/下降——不用物理引擎，绝不卡死在台阶前。
        target_y = get_ground_height(self.x, self.z, self.y)
        self.y = lerp(self.y, target_y, min(time.dt * GROUND_LERP_SPEED, 1.0))

        # ---- 潜行时的呼吸声：近距怪物能听见（屏息可消除 → 屏息的真实价值）----
        if sneaking and not self.is_holding_breath:
            nearest_m = None
            for m in list(MONSTERS):
                if m.is_dead:
                    continue
                d = dist_xz(m.position, self.position)
                if nearest_m is None or d < nearest_m:
                    nearest_m = d
            if nearest_m is not None and nearest_m < 6.0:
                self.sneak_breath_timer -= dt
                if self.sneak_breath_timer <= 0:
                    self.sneak_breath_timer = 1.2
                    emit_noise(self.position, SNEAK_BREATH_NOISE)
                    print('（你的呼吸声在寂静里太明显了……按住 Q 屏住呼吸！）')
        else:
            self.sneak_breath_timer = 0.0

        # ---- 视点：基础高度 + 常态呼吸浮动 + 恐惧发抖（怪物逼近）----
        self._base_h = lerp(self._base_h, STAND_HEIGHT, min(dt * 8, 1))
        breath_float = math.sin(pytime.time() * 1.3) * 0.012   # ★ 常态呼吸浮动
        self.camera_pivot.y = self._base_h + breath_float \
            + math.sin(pytime.time() * 9.3) * 0.007 * danger_k
        self.camera_pivot.x = math.sin(pytime.time() * 11.0) * 0.009 * danger_k
        if self._shake_t > 0:                   # ★ 规格三.3：math.sin 高频重量感晃动
            self._shake_t = max(0.0, self._shake_t - dt)
            _sk = self._shake_t / 0.35
            self.camera_pivot.x += math.sin(pytime.time() * 80.0) * 0.05 * _sk
            self.camera_pivot.y += math.cos(pytime.time() * 71.0) * 0.035 * _sk

        # ---- UI 同步：体力条（绿）常驻 ----
        stamina_fill.scale = Vec3(0.62 * self.stamina / BASE_MAX_STAMINA, 0.03, 1)
        stamina_fill.color = (color.rgb(70, 150, 60) if self.stamina <= 0
                              else color.rgb(60, 220, 90))


# =====================================================================================
#  ★ 第三关专属实体类（核心实验室）：推拉门 / 应急闪烁灯 / 血迹 / 破碎的镜子 /
#    玻璃培养罐 / 手术台 / 残缺实验报告 / 门禁卡 / 主控门
# =====================================================================================
def resolve_door_collision(entity):
    """★ 关闭的推拉门与主控门当作障碍物：把实体推出门板（门开启后不再阻挡）。
    本项目移动为自驱（position += 速度），引擎碰撞体不会自动阻挡——
    因此门板的阻挡在这里用与墙体一致的 AABB 推出解算实现。"""
    if entity is None or getattr(entity, 'is_dead', False):
        return
    for d in list(DOORS) + list(MAIN_DOORS):    # ★ 浅拷贝遍历
        if getattr(d, 'is_dead', False):
            continue
        if isinstance(d, LabDoor) and d.open:
            continue                            # 已滑开的门：可通过
        if d.axis == 'z':
            hx, hz = 0.3, d.length / 2.0        # 门板长边沿 Z
        else:
            hx, hz = d.length / 2.0, 0.3        # 门板长边沿 X
        nearest_x = clamp(entity.x, d.x - hx, d.x + hx)
        nearest_z = clamp(entity.z, d.z - hz, d.z + hz)
        dx = entity.x - nearest_x
        dz = entity.z - nearest_z
        dist_sq = dx * dx + dz * dz
        r = 0.55
        if dist_sq >= r * r:
            continue                            # 没贴到门板
        if dist_sq <= 1e-9:
            # 中心陷入门板：沿穿透最浅的水平轴推出
            if hx - abs(entity.x - d.x) <= hz - abs(entity.z - d.z):
                entity.x = d.x + (hx + r) * (1 if entity.x >= d.x else -1)
            else:
                entity.z = d.z + (hz + r) * (1 if entity.z >= d.z else -1)
        else:
            dist = math.sqrt(dist_sq)
            push = r - dist
            entity.x += dx / dist * push
            entity.z += dz / dist * push


class AmbientSound3D(Entity):
    """★ 房间 3D 环境音（本轮新增）：挂在房间里的"隐藏实体"（无模型不可见），
    循环播放环境音效。规格实现：
      · 音频以 Audio(..., loop=True, autoplay=False, is_3d=True) 加载（规格写法），
        每帧更新 audio.position = 实体位置——玩家靠近才能听见、走远渐渐消失；
      · 加载严格 try-except：用户还没下载音频文件时 print 提示，
        实体仍存在但静音，绝不报错中断游戏。
    第三关布点：监控室中心 → clock_tick；停尸房角落 → water_drip。"""

    def __init__(self, position, sound_name, base_volume=0.9, hear_range=9.0):
        """环境音为手动线性衰减（规格一.3）：音量 = base × (1 - d/hear_range)，
        >20 米暂停（见 update）——与怪物音频同一套距离逻辑。"""
        super().__init__(position=position)     # ★ 隐藏实体：无模型不可见
        self.is_dead = False
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）
        self.sound_name = sound_name
        self.base_volume = base_volume
        self.hear_range = hear_range
        # ★ 3D 音频加载（规格：loop=True + autoplay=False + is_3d=True）；
        #   load_3d_audio 内部已 try-except：缺失时打印"提示/警告"并返回 None。
        self.audio = load_3d_audio(sound_name, loop=True, volume=0.0)
        try:
            if self.audio is not None:
                self.audio.play()               # 循环播放开始（音量由距离驱动）
        except Exception:
            pass                                # 播放失败不影响游戏
        AMBIENT_SOUNDS3D.append(self)

    def update(self):
        # ★ 防闪退铁律第一行
        if not entity_gate(self) or self.is_dead:
            return
        if self.audio is None:
            return                              # 音频缺失：静音运行
        # ★ 每帧更新 3D 音效位置（规格：position 绑定到实体所在房间中心）
        set_audio_position(self.audio, self.position)
        # 距离音量模拟：靠近渐响、走远渐弱；
        # ★ 规格二.3：超过 20 米暂停播放（省性能），回到近场自动恢复
        if player is not None:
            d = dist_xz(self.position, player.position)
            try:
                if d > 20.0:
                    self.audio.volume = 0.0        # ★ 远场静音
                    if self.audio.playing:
                        self.audio.pause()
                else:
                    if not self.audio.playing:
                        self.audio.play()
                    self.audio.volume = self.base_volume * clamp(
                        1 - d / self.hear_range, 0, 1)
            except Exception:
                pass


class Crawler(Monster):
    """★ 盲蛛实体怪（规格二）：不新增模型——用聆听者身体压低拼凑成爬行怪。
    听到声音会缓慢靠近（追击速度减半、巡逻减速），共用状态机与突脸判定。"""

    def __init__(self, spawn_tile=None, world_pos=None):
        super().__init__(spawn_tile, world_pos=world_pos)
        self.kind = 'crawler'
        self.scale = Vec3(1.0, 0.5, 1.0)        # 压低身形——贴地爬行
        self._base_scale = Vec3(1.0, 0.5, 1.0)  # ★ 爬行怪原始比例（复位用）


class LabDoor(Entity):
    """推拉门（第三关）：横在房间入口、带碰撞体的黑色门板。
    · 静音开门：靠近按 E——门沿墙横向平移 2 米（animate_position，1.5 秒），
      播放开门声 sfx_door_open（缺失时合成吱呀声），不产生任何噪音（规格）；
      开门后 7~11 秒自动滑回关闭，播放关门声 sfx_door_close（规格）。
    · 暴力撞门：玩家奔跑速度 > 8 撞向门（Player.update 检测）→ 瞬间平移开启，
      播放巨大"砰"声并向所有怪物广播门的位置（吸引怪物，规格）；
      被撞开的门轨道已损坏，不会再自动关闭。"""

    def __init__(self, cx, cz, length, axis='z'):
        """axis='z'：门板长边沿 Z（走廊侧墙上的门），沿 Z 滑动；
        axis='x'：门板长边沿 X（走廊尽头的门），沿 X 滑动。"""
        sc = ((0.4, 3.6, length) if axis == 'z' else (length, 3.6, 0.4))
        super().__init__(model='cube', position=(cx, 1.8, cz), scale=sc,
                         color=color.rgb(30, 32, 38))
        self.is_dead = False
        self.initialized = True                 # ★ 构造完成：允许进入 update（规格）
        self.axis = axis
        self.length = length
        self.slide_dir = (Vec3(0, 0, 2.0) if axis == 'z' else Vec3(2.0, 0, 0))
        self.closed_pos = Vec3(cx, 1.8, cz)
        self.open = False
        add_box_collider(self, size=Vec3(sc[0], sc[1], sc[2]))
        DOORS.append(self)

    def silent_open(self):
        """★ 静音开门（规格）：1.5 秒横向平移 2 米 + 播放开门声 sfx_door_open
        （用户 mp3 缺失时自动退化为合成吱呀声），不产生任何噪音。
        开门后 7~11 秒自动关闭（自动关门时播放 sfx_door_close）。"""
        if self.open:
            return
        self.open = True
        play_sfx('door_open', volume=0.5, pitch=random.uniform(0.9, 1.1))
        try:
            self.animate_position(self.closed_pos + self.slide_dir,
                                  duration=1.5, curve=curve.in_out_expo)
        except Exception:
            self.position = self.closed_pos + self.slide_dir
        try:
            self.collision = False              # 滑开后不再阻挡
        except Exception:
            pass
        # ★ 自动关闭逻辑（规格建议）：开门后 7~11 秒滑回原位并播放关门声
        try:
            invoke(self.auto_close, delay=random.uniform(7.0, 11.0))
        except Exception:
            pass

    def auto_close(self):
        """定时自动关闭（invoke 延迟回调）：门已损坏/已手动关闭则跳过"""
        if self.is_dead or not self.open:
            return
        self.close()

    def close(self):
        """★ 关门（规格）：滑回原位 + 播放关门声 sfx_door_close
        （用户 mp3 缺失时自动退化为合成关门声）；动画结束后恢复阻挡。"""
        if self.is_dead or not self.open:
            return
        self.open = False
        play_sfx('door_close', volume=0.55, pitch=random.uniform(0.9, 1.1))
        try:
            self.animate_position(self.closed_pos,
                                  duration=1.2, curve=curve.in_out_expo)
        except Exception:
            self.position = self.closed_pos
        try:
            invoke(self._restore_collision, delay=1.25)   # 动画结束再恢复阻挡
        except Exception:
            self._restore_collision()

    def _restore_collision(self):
        """关门动画结束后恢复碰撞阻挡（避免夹住站在门口的玩家/怪物）"""
        if self.is_dead or self.open:
            return
        try:
            self.collision = True
        except Exception:
            pass

    def bash_open(self):
        """★ 暴力撞门：瞬间平移开启 + 巨大"砰"声 + 向所有怪物广播门位置（规格）。
        被撞开的门轨道已损坏——不再自动关闭，因此没有关门声。"""
        if self.open:
            return
        self.open = True
        self.position = self.closed_pos + self.slide_dir
        play_sfx('door_bang', volume=1.0)
        emit_noise(self.position, 25.0)   # ★ 规格四.3：暴力撞门噪音半径 25
        print('【巨响】砰！！——你撞开了门，整条走廊都听见了！')
        try:
            self.collision = False
        except Exception:
            pass

    def update(self):
        if not entity_gate(self):
            return


class WarningLight(Entity):
    """应急闪烁灯（第三关）：走廊顶部的红色发光方块 + 红色点光。
    按最近怪物与玩家的距离驱动（规格）：
      距离 > 15 → 极暗（alpha=10）；距离 < 12 → sin(time*20) 失控快闪；
      12~15 之间 → 缓慢呼吸。"""

    def __init__(self, cx, cz):
        super().__init__(model='cube', position=(cx, 3.8, cz),
                         scale=(0.5, 0.18, 0.5), color=color.rgba(255, 0, 0, 10))
        self.is_dead = False
        self.initialized = True
        try:
            self.lamp = PointLight(parent=self, color=color.rgba(255, 40, 40, 60),
                                   distance=5.0, shadows=False)   # ★ 规格三.1 红光淡化
        except Exception:
            self.lamp = None
        WARNING_LIGHTS.append(self)
        # ★ 规格一.2：应急灯 3D 电流嗡鸣
        AmbientSound3D(Vec3(cx, 3.8, cz), 'fuse_hum',
                       base_volume=0.4, hear_range=7.0)

    def update(self):
        if not entity_gate(self):
            return


class DripPipe(Revealable):
    """★ 滴水管道（规格二.1）：走廊墙顶的极暗圆柱管道（程序化圆柱网格），
    回声扫过显出青白轮廓；管道下方隐藏 3D 音源循环播放 sfx_water_drip"""

    def __init__(self, cx, cz, base_y=3.55):
        global _PIPE_MESH
        if _PIPE_MESH is None:
            _PIPE_MESH = _cylinder_mesh(sides=8, radius=0.5, height=1.0)
        super().__init__(
            base_color=color.rgb(8, 8, 9),
            model=_PIPE_MESH,
            position=(cx, base_y, cz),
            rotation_x=90, scale=(0.45, 10.0, 0.45),   # 躺平沿走廊延伸 10 米
        )
        self.is_dead = False
        self.initialized = True
        DRIP_PIPES.append(self)
        # ★ 规格一.3：管道下方隐藏 3D 水滴声源（循环，距离驱动音量）
        AmbientSound3D(Vec3(cx, base_y - 0.6, cz), 'water_drip',
                       base_volume=0.8, hear_range=10.0)

    def update(self):
        if not entity_gate(self):
            return


class ElecBox(Revealable):
    """★ 漏电电线与破损配电箱（规格二.2）：墙上的暗色箱体 + 两根垂落细电线，
    回声可扫出轮廓；绑定 3D 电流嗡鸣（sfx_electricity_hum / fuse_hum 兜底）"""

    def __init__(self, cx, cz, ry=90.0, base_y=1.6):
        super().__init__(
            base_color=color.rgb(8, 8, 9),
            model='cube',
            position=(cx, base_y, cz), rotation_y=ry,
            scale=(0.18, 0.7, 0.5),
        )
        self.is_dead = False
        self.initialized = True
        for i in range(2):                      # 两根细电线沿墙垂落
            Entity(parent=self, model='cube',
                   position=(0, -0.5 - i * 0.35, 0.08 - i * 0.16),
                   scale=(0.35, 0.32, 0.04), color=color.rgb(30, 28, 26))
        ELEC_BOXES.append(self)
        AmbientSound3D(Vec3(cx, base_y, cz), 'elec_hum',
                       base_volume=0.5, hear_range=7.0)

    def update(self):
        if not entity_gate(self):
            return
        if not entity_gate(self) or self.is_dead or player is None:
            return
        d = None
        for m in list(MONSTERS):            # ★ 浅拷贝遍历
            if m.is_dead:
                continue
            dd = dist_xz(m.position, player.position)
            if d is None or dd < d:
                d = dd
        if d is None:
            d = 999.0
        if d > 15:
            self.color = color.rgba(255, 0, 0, 10)            # 极暗（规格 alpha=10）
        elif d < 12:
            # ★ 失控快闪：math.sin(time.time()*20) 驱动 alpha 高低跳变
            flicker = math.sin(pytime.time() * 20.0) > 0
            self.color = color.rgba(255, 0, 0, 220 if flicker else 30)
        else:
            b = 0.5 + 0.5 * math.sin(pytime.time() * 3.0)
            self.color = color.rgba(255, 0, 0, int(40 + 40 * b))


class BloodPool(Entity):
    """血迹（第三关）：地面的红色贴片。玩家踩上（距离<1）→ 移动速度 ×0.5、
    脚步声变为黏腻的 squish（均由 Player.update 处理）。"""

    def __init__(self, cx, cz, y=0.06, size=3.0, rgba=(120, 10, 15, 200), rot=0):
        super().__init__(model='quad', position=(cx, y, cz),
                         rotation=(90, rot, 0), scale=(size, size),
                         color=color.rgba(*rgba), double_sided=True)
        self.is_dead = False
        self.initialized = True
        BLOODPOOLS.append(self)

    def update(self):
        if not entity_gate(self):
            return


def try_loot_report(obj, cx, cz, base_y=0.0):
    """★ 规格三：搜查掉落——30% 概率在物件旁生成一份实验报告（只生成一次）；
    失败播放"空空如也"反馈。报告继承既有逻辑：E 阅读 / R 收集。"""
    if getattr(obj, 'searched', False):
        print('【搜查】这里已经搜过了……')
        return False
    obj.searched = True
    play_sfx('door_creak', volume=0.45)         # 翻找音效
    if random.random() < 0.3:
        _fid, _ftxt = next_fragment()
        LabReport(cx, cz + 1.4, base_y=base_y, text=_ftxt, frag_id=_fid)
        print('【搜查】哗啦——一份残缺的实验报告掉了出来！')
        return True
    print('【搜查】空的……什么都没有。')
    play_sfx('buzz', volume=0.18)
    return False


def spawn_blood_stain(cx, cz, y=0.02):
    """★ 不规则血迹簇（规格二.2）：2~3 片随机旋转/尺寸的暗红 Quad 叠加成
    不规则形状（贴地，y 可区分走廊簇/手术台簇）；踩上减速 50% + 黏腻脚步"""
    for _ in range(random.randint(2, 3)):
        BloodPool(cx + random.uniform(-0.5, 0.5),
                  cz + random.uniform(-0.5, 0.5),
                  y=y, size=random.uniform(0.9, 1.8),
                  rgba=(80, 0, 0, 200),
                  rot=random.uniform(0, 180))


class BrokenMirror(Revealable):
    """破碎的镜子（第三关）：贴在墙上的白色四边形。
    回声波纹扫过时：高亮显形 + 触发一次特殊的高频玻璃音（EchoSphere 处理）。"""

    def __init__(self, cx, cz, rotation_y):
        super().__init__(
            base_color=color.rgba(220, 225, 235, 90),
            model='quad', position=(cx, 1.6, cz), rotation_y=rotation_y,
            scale=(2.2, 1.4), double_sided=True,
        )
        MIRRORS.append(self)

    def update(self):
        if not entity_gate(self):
            return


class GlassTank(Revealable):
    """玻璃培养罐（第三关）：绿色半透明方柱（★ 规格三.1：alpha 调低只显隐约轮廓），
    阻挡通行；回声沉闷回音。"""

    def __init__(self, cx, cz, base_y=0.0):
        """base_y：所在楼层地板高度（地下室传 -5.0，罐体立于该层地板上）"""
        super().__init__(
            base_color=color.rgba(0, 255, 0, 40),
            model='cube', position=(cx, base_y + 1.3, cz),
            scale=(0.9, 2.6, 0.9),
        )
        self.searched = False                # ★ 规格三：可搜查（30% 报告）
        add_box_collider(self, size=Vec3(0.9, 2.6, 0.9))   # ★ 阻挡通行
        TANKS.append(self)

    def search(self):
        """★ 规格三：搜查掉落——30% 实验报告（一次），否则空空如也"""
        try_loot_report(self, self.x, self.z,
                        base_y=self.base_y if hasattr(self, 'base_y') else 0.0)

    def update(self):
        if not entity_gate(self):
            return


class OperatingTable(Entity):
    """手术台（第三关）：房间中心的立方体。按 E 搜查（每台一次）：
    50% 弹出实验报告 / 30% 获得门禁卡 / 20% 为空（规格概率）。"""

    def __init__(self, cx, cz):
        super().__init__(model='cube', position=(cx, 0.55, cz),
                         scale=(2.0, 1.1, 0.9), color=color.rgb(14, 15, 17))
        self.is_dead = False
        self.initialized = True
        self.searched = False
        add_box_collider(self, size=Vec3(2.0, 1.1, 0.9))
        TABLES.append(self)

    def search(self):
        """★ 规格三：搜查掉落——30% 实验报告（一次），否则空空如也"""
        try_loot_report(self, self.x, self.z)

    def update(self):
        if not entity_gate(self):
            return


class Drawer(Entity):
    """抽屉柜（第三关）：三屉金属方柜，按 E 搜查（每只一次）：
    45% 空 / 35% 恢复体力与氧气 / 20% 金属哐当惊吓（巨大噪音暴露位置）。"""

    def __init__(self, cx, cz, base_y=0.0, ry=0.0):
        super().__init__(model='cube', position=(cx, base_y + 0.9, cz),
                         scale=(1.1, 1.8, 0.7), color=color.rgb(18, 20, 24),
                         rotation_y=ry)
        self.is_dead = False
        self.initialized = True                 # ★ entity_gate 闸门
        self.searched = False
        add_box_collider(self, size=Vec3(1.1, 1.8, 0.7))
        for i in range(3):                      # 三块抽屉面板 + 金属把手（视觉细节）
            Entity(parent=self, model='cube',
                   position=(0, 0.5 - i * 0.55, -0.38),
                   scale=(0.9, 0.38, 0.05), color=color.rgb(70, 76, 86))
            Entity(parent=self, model='cube',
                   position=(0, 0.5 - i * 0.55, -0.43),
                   scale=(0.3, 0.06, 0.04), color=color.rgb(150, 130, 90))
        DRAWERS.append(self)

    def search(self):
        """★ 规格三：搜查掉落——30% 实验报告（一次），否则空空如也"""
        try_loot_report(self, self.x, self.z, base_y=self.base_y
                        if hasattr(self, 'base_y') else 0.0)


class LabReport(Entity):
    """残缺实验报告（第三关）：白色发光四边形，贴地旋转。
    按 E 阅读：弹出预分配的实验报告文本（构造时从洗牌池中取得，同局不重复）；
    ★ 阅读不自动收起——按 E 关闭 / 按 R 拾取（规格三.3），可反复阅读。"""

    def __init__(self, cx, cz, text='', base_y=0.0, frag_id=None):
        """base_y：所在楼层地板高度（地下室传 -5.0）"""
        super().__init__(model='quad', position=(cx, base_y + 0.12, cz),
                         rotation_x=90, scale=(0.7, 1.0),
                         color=color.rgba(255, 255, 255, 210), double_sided=True)
        self.is_dead = False
        self.initialized = True
        self.base_y = base_y
        # ★ 规格四.2/四.3：空文本容错
        self.text = text if text else '这段记录已经被血迹模糊，无法辨认……'
        self.frag_id = frag_id              # ★ 绑定碎片池 ID（拾取时写入存档）
        self.spin_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.8, 0.4, 1.0))
        REPORTS.append(self)

    def read(self):
        """★ 阅读：弹出预分配文本 → UI 显示 3 秒；报告销毁（一次性不重复）"""
        txt = self.text                # 先捕获（safe_destroy 后仍可用）
        safe_destroy(self)             # ★ 同一个报告不能重复阅读
        open_diary(txt)                # 冻结 3 秒阅读

    def update(self):
        if not entity_gate(self) or self.is_dead:
            return
        self.spin_t += time.dt
        self.rotation_y = (self.rotation_y + 70 * time.dt) % 360   # ★ 贴地旋转
        b = 0.6 + 0.4 * math.sin(self.spin_t * 2.5)
        self.color = color.rgba(255, 255, 255, int(140 + 90 * b))  # 白色发光脉动


class Keycard(Entity):
    """红色门禁卡（第三关）：漂浮旋转的红卡，按 E 拾取；
    携带它靠近主控门按 E 即可通关。"""

    def __init__(self, cx, cz, base_y=0.0):
        """base_y：所在楼层地板高度（地下室传 -5.0，卡片悬浮于其上方 0.7 米）"""
        super().__init__(model='cube', position=(cx, base_y + 0.7, cz),
                         scale=(0.45, 0.06, 0.3), color=color.rgb(255, 45, 45))
        self.is_dead = False
        self.initialized = True
        self.base_y = base_y
        self.pulse_t = random.uniform(0, math.tau)
        add_box_collider(self, size=Vec3(0.5, 0.3, 0.4))
        KEYCARDS.append(self)

    def update(self):
        if not entity_gate(self) or self.is_dead:
            return
        self.pulse_t += time.dt
        self.rotation_y += 80 * time.dt
        self.y = self.base_y + 0.7 + 0.12 * math.sin(self.pulse_t * 2.0)
        self.color = color.rgb(255, int(40 + 50 * abs(math.sin(self.pulse_t * 3))), 45)


class MainDoor(Entity):
    """主控门（第三关）：走廊尽头带碰撞体的金属大门。
    携带红色门禁卡靠近按 E → 触发 WIN；未携带 → 刷卡器拒绝提示。"""

    def __init__(self, cx, cz):
        super().__init__(model='cube', position=(cx, 1.8, cz),
                         scale=(2.4, 3.6, 0.5), color=color.rgb(14, 11, 9))
        self.is_dead = False
        self.initialized = True
        self.axis = 'x'
        self.length = 2.4
        # 门上的红色刷卡指示灯（呼吸闪烁）
        Entity(parent=self, model='sphere', scale=0.09,
               position=(0.8, 0.6, -0.32), color=color.rgb(255, 40, 40))
        add_box_collider(self, size=Vec3(2.4, 3.6, 0.5))
        MAIN_DOORS.append(self)

    def update(self):
        if not entity_gate(self) or self.is_dead:
            return
        b = 0.5 + 0.5 * math.sin(pytime.time() * 3.0)
        for ind in self.children:           # ★ 浅拷贝遍历
            ind.color = color.rgb(255, int(40 + 60 * b), 40)


# =====================================================================================
#  八、关卡管理器：第一关（40x40）与第二关（地下二层：多层楼梯/柜子/管子/多出口）
# =====================================================================================
class LevelManager:
    """关卡管理器：DFS 迷宫生成、实体放置、地块换算、BFS 寻路、场景销毁。
      · load_level(1)：潮湿回廊——40x40 迷宫，3 保险丝 + 1 出口 + 怪物生态
      · load_level(2)：地下二层——30x30 迷宫，★ 出生高台(下行楼梯) + 真实出口
        高台(上行楼梯) + 4 柜子 + 3 管子 + 10 日记 + 三出口(1 真) + 怪物生态
    ★ 扩展新关卡：仿照 _load_level_2 写一个新分支即可（辅助函数全部可复用）。"""

    def __init__(self):
        self.grid = []
        self.grid_n = GRID_L1
        self.floor_tiles = []
        self.dead_ends = []
        self.spawn_tile = (1, 1)
        self.ground = None
        self.exit_gates = []          # 第二关为多出口列表；第一关只有 1 个
        self.open_points = []         # ★ 第三关（无网格）的开阔点：怪物游荡/卡墙保护
        self.player = None

    # ---------------- 地块换算 ----------------
    def tile_to_world(self, tile):
        x, z = tile
        return Vec3((x - (self.grid_n - 1) / 2) * TILE, 0,
                    (z - (self.grid_n - 1) / 2) * TILE)

    def world_to_tile(self, pos):
        return (round(pos.x / TILE + (self.grid_n - 1) / 2),
                round(pos.z / TILE + (self.grid_n - 1) / 2))

    def is_floor(self, tile):
        x, z = tile
        return 0 <= x < self.grid_n and 0 <= z < self.grid_n and self.grid[z][x] == 0

    def _neighbors(self, tile):
        x, z = tile
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, z + dz)
            if self.is_floor(nb):
                yield nb

    # ---------------- BFS ----------------
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

    # ---------------- 通用放置辅助 ----------------
    def _pick_spread_tiles(self, pool, count, min_gap, used):
        """从池中挑选彼此保持最小间距（曼哈顿格距）的地块"""
        random.shuffle(pool)
        picked = []
        for t in pool:
            if t in used:
                continue
            if all(abs(t[0] - o[0]) + abs(t[1] - o[1]) >= min_gap for o in picked):
                picked.append(t)
                used.add(t)
            if len(picked) >= count:
                break
        while len(picked) < count:            # 兜底放宽
            t = random.choice([x for x in self.floor_tiles if x not in used])
            picked.append(t)
            used.add(t)
        return picked

    def _build_geometry(self):
        """地面（★ 带地形碰撞体，射线高度检测的基准面）+ 逐地块墙体"""
        span = self.grid_n * TILE
        # ★ 显式三元组 scale（XZ 平铺、Y 不缩放），保证地面完整覆盖整张地图
        self.ground = Entity(model='plane', scale=(span, 1, span),
                             color=color.rgb(8, 8, 8))     # ★ 规格一.2：地面极暗深灰
        self.ground.is_dead = False
        self.ground.is_terrain = True          # ★ 地形标记
        self.ground.walk_top = 0.0             # ★ 顶面高度（解析判定用）
        WALKABLES.append(self.ground)          # ★ 注册可行走表面（地面）
        # 地面碰撞体：薄盒子，顶面正好在 y=0
        add_box_collider(self.ground, center=Vec3(0, -0.5, 0),
                         size=Vec3(span, 1.0, span))
        apply_lit_shader(self.ground)
        for z in range(self.grid_n):
            for x in range(self.grid_n):
                if self.grid[z][x] == 1:
                    w = self.tile_to_world((x, z))
                    WALLS.append(Wall(w.x, w.z))

    def _build_terrain_l2(self, real_exit_tile):
        """★ 第二关多层地形（"楼梯走不了"修复的落地）：
        ① 出生高台（y=3.0）+ 一段下行楼梯 → 玩家开局从台上走下进入迷宫；
        ② 真实出口高台（y=2.5）+ 一段上行楼梯 → 出口建在高台上，必须爬楼梯抵达。
        台阶均为带 BoxCollider 的立方体（视觉），并注册解析斜坡（射线回退）。"""
        # ---- ① 出生高台 + 下行楼梯 ----
        sp = self.tile_to_world(self.spawn_tile)
        build_platform(sp.x, sp.z, 3.0)
        for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if self.is_floor((self.spawn_tile[0] + dx, self.spawn_tile[1] + dz)):
                nb = self.tile_to_world((self.spawn_tile[0] + dx,
                                         self.spawn_tile[1] + dz))
                # ★ 上升方向 = 从相邻格"指向平台"（邻居在 +x 侧则向 -x 爬）
                direction = ('-x' if dx > 0 else '+x') if dx != 0 \
                    else ('-z' if dz > 0 else '+z')
                # 楼梯底端在相邻走廊格中心，向高台方向上升 3 米（run=一格 4 米）
                Stairs(nb.x, nb.z, 0.0, 3.0, TILE, 2.4, direction, 6)
                break
        # ---- ② 真实出口高台 + 上行楼梯 ----
        ep = self.tile_to_world(real_exit_tile)
        build_platform(ep.x, ep.z, 2.5)
        ex, ez = real_exit_tile
        for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if self.is_floor((ex + dx, ez + dz)):
                nb = self.tile_to_world((ex + dx, ez + dz))
                direction = ('-x' if dx > 0 else '+x') if dx != 0 \
                    else ('-z' if dz > 0 else '+z')
                Stairs(nb.x, nb.z, 0.0, 2.5, TILE, 2.4, direction, 5)
                break

    # ---------------- 关卡加载 ----------------
    def load_level(self, level_id):
        self.teardown()
        if level_id == 2:
            self._load_level_2()
        elif level_id == 3:
            self._load_level_3()
        else:
            self._load_level_1()

    def nearest_open_point(self, pos):
        """★ 最近的可行走开阔点（返回世界坐标 Vec3）：
        迷宫关（L1/L2）取网格最近地板格；硬编码关（L3）取 open_points 最近点。
        供卡墙保护把陷入墙体的实体推向开阔地。"""
        if self.grid:
            return self.tile_to_world(self.nearest_floor_tile(pos))
        best, best_d = None, 10 ** 18
        for p in self.open_points:              # ★ 浅拷贝语义遍历
            d = (p.x - pos.x) ** 2 + (p.z - pos.z) ** 2
            if d < best_d:
                best, best_d = p, d
        return best if best is not None else Vec3(0, 0, 0)

    def _lab_block(self, cx, cz, sx, sz, cy=None, sy=None):
        """第三关：一面带碰撞体的黑色墙块（加入 WALLS——碰撞/回声/小地图全部复用）。
        cy/sy：可选的竖直中心与厚度——地下室墙体（Y=-5 层）需要自定义 y 范围。"""
        w = Wall(cx, cz)
        if cy is None or sy is None:
            w.position = (cx, WALL_HEIGHT / 2, cz)
            w.scale = (sx, WALL_HEIGHT, sz)
            add_box_collider(w, size=Vec3(sx, WALL_HEIGHT, sz))
        else:
            w.position = (cx, cy, cz)
            w.scale = (sx, sy, sz)
            add_box_collider(w, size=Vec3(sx, sy, sz))
        WALLS.append(w)                       # ★ 与 L1/L2 一致：墙块登记进 WALLS
        return w

    def _load_level_3(self):
        """★ 第三关「核心实验室」（规格一 重构：30×30 DFS 迷宫骨架，120×120 米
        = 旧版 80×80 的 1.5 倍）——生成器自带打环，走廊满是岔路口与死胡同；
        五个房间藏进偏僻角落：停尸房+手术室（西簇相邻·互通门）、
        监控室+储藏室（东簇相邻·互通门）、档案室（北角独居）——
        房间互通形成环形路线；房内承重断柱打破空旷感；
        2F（Y=6）为同构迷宫矮墙（2.4 米），两部上行楼梯 + 地下室竖井（门禁卡）；
        手术台/抽屉/培养罐搜查 30% 掉落实验报告（规格三）。"""
        global player
        # ================= 1F 迷宫骨架（岔路口 + 死胡同） =================
        self.grid_n = 30
        self.grid = generate_maze_grid(30)
        # ---- 房间布局（规格一.3：偏僻角落；A/B 两簇相邻以便互通）----
        # ★ 规格二：10 个房间——3 文本房（30%：停尸房/监控室/档案室）
        #   + 7 布景房（70%：手术室/储藏室/卫生间/杂物间/配电房/病房/值班室）
        rooms = {
            'morgue':  (2, 12, 3, 2),    # 文本房（报告+日记）
            'surgery': (2, 14, 3, 2),    # 布景房（手术台+血迹；与停尸房互通）
            'monitor': (25, 10, 3, 2),   # 文本房（报告）
            'storage': (25, 12, 3, 2),   # 布景房（与监控室互通）
            'archive': (13, 2, 3, 2),    # 文本房（日记）
            'bath':    (7, 20, 3, 2),    # 布景房：卫生间（洗手台+镜）
            'junk':    (20, 20, 3, 2),   # 布景房：杂物间（倒塌推车+纸箱）
            'power':   (7, 4, 3, 2),     # 布景房：配电房（配电箱+管线）
            'ward':    (20, 4, 3, 2),    # 布景房：病房（破损病床+血迹）
            'duty':    (13, 24, 3, 2),   # 布景房：值班室（病床+柜）
        }
        for (rx, rz, rw, rh) in rooms.values():
            for _x in range(rx, rx + rw):
                for _z in range(rz, rz + rh):
                    self.grid[_z][_x] = 0
        self._collect_tiles()

        # ---- 连通性修复：保证房间主门外格与迷宫主体连通（有界循环，绝不死循环）----
        def _carve_until_reachable(tile):
            """从 tile 沿 ±z 逐格清墙直至接入迷宫主体（≤30 步）"""
            x, z = tile
            for step in range(1, 31):
                for nz in (z + step, z - step):
                    if 1 <= nz < 29:
                        self.grid[nz][x] = 0
                        if self.bfs_distances((1, 1)).get((x, nz)) is not None:
                            return
            self.grid[z][x] = 0

        # 主门外格（西半朝西 / 东半朝东 / 北排朝南 / 南排朝北）
        door_out = {}
        for name, (rx, rz, rw, rh) in rooms.items():
            zc = rz + rh // 2
            xc = rx + rw // 2
            if rx + rw // 2 <= 15:                # 西半区：门朝西
                door_out[name] = (rx - 1, zc)
            else:                                  # 东半区：门朝东
                door_out[name] = (rx + rw, zc)
        for t in door_out.values():
            x, z = t
            if 1 <= x < 29 and 1 <= z < 29:
                self.grid[z][x] = 0
        for t in door_out.values():
            if self.bfs_distances((1, 1)).get(t) is None:
                _carve_until_reachable(t)
        self._collect_tiles()

        # ---- 1F 迷宫墙（4×4×4 实心立方，与 L1/L2 同构；房间格已清）----
        for _z in range(self.grid_n):
            for _x in range(self.grid_n):
                if self.grid[_z][_x] == 1:
                    _w = self.tile_to_world((_x, _z))
                    WALLS.append(Wall(_w.x, _w.z))   # ★ 手动注册（Wall 不自登记）

        # ---- 地面（120×120，walkable + 碰撞）----
        self.ground = Entity(model='plane', scale=(130, 1, 130),
                             color=color.rgb(8, 8, 8))
        self.ground.is_dead = False
        self.ground.is_terrain = True
        self.ground.walk_top = 0.0
        WALKABLES.append(self.ground)
        add_box_collider(self.ground, center=Vec3(0, -0.5, 0),
                         size=Vec3(130, 1.0, 130))
        apply_lit_shader(self.ground)

        # ================= 房间薄墙 + 主门 + 互通门（规格二） =================
        def _wall_line(axis, const, a0, a1, gaps):
            """沿墙线建薄墙（自动避开 gaps=[(g0,g1)] 门洞区间）"""
            segs, cur = [], a0
            for (g0, g1) in sorted(gaps):
                if g0 > cur + 0.1:
                    segs.append((cur, g0))
                cur = max(cur, g1)
            if cur < a1 - 0.1:
                segs.append((cur, a1))
            for (s0, s1) in segs:
                c, ln = (s0 + s1) / 2, s1 - s0
                if axis == 'x':                  # 墙线沿 X（z=const）
                    self._lab_block(c, const, ln, 0.6)
                else:                            # 墙线沿 Z（x=const）
                    self._lab_block(const, c, 0.6, ln)

        def _room_bounds(r):
            rx, rz, rw, rh = r
            wx0 = (rx - 14.5) * 4 - 2
            wx1 = (rx + rw - 1 - 14.5) * 4 + 2
            wz0 = (rz - 14.5) * 4 - 2
            wz1 = (rz + rh - 1 - 14.5) * 4 + 2
            return wx0, wx1, wz0, wz1

        # ★ 通用房间构建器：主门（西/东）+ 可选互通门 + 承重断柱
        # 互通对：morgue↔surgery（共享 z 边界）、monitor↔storage（共享 z 边界）
        inter_pairs = {('morgue', 'surgery'), ('monitor', 'storage')}
        door_specs = []                          # (世界x, 世界z, axis)
        built_edges = set()                      # 已建边界（防互通墙重复封死）
        for name, r in rooms.items():
            wx0, wx1, wz0, wz1 = _room_bounds(r)
            rcx, rcz = (wx0 + wx1) / 2, (wz0 + wz1) / 2
            west = (rx_mid := (r[0] + r[2] / 2)) <= 15
            if west:                              # 主门朝西（x=wx0）
                _wall_line('z', wx0, wz0, wz1, [(rcz - 2, rcz + 2)])
                door_specs.append((wx0, rcz, 'z'))
            else:                                 # 主门朝东（x=wx1）
                _wall_line('z', wx1, wz0, wz1, [(rcz - 2, rcz + 2)])
                door_specs.append((wx1, rcz, 'z'))
            # 南北边界（互通对共享的那条只建一次，带门洞）
            partner = next((b for (a, b) in inter_pairs if a == name), None)
            host = next((a for (a, b) in inter_pairs if b == name), None)
            if host is not None:
                # 本房是互通对的"下房"：南边界与 host 的北边界共享——由 host 建
                if ('N', wz1) not in built_edges:
                    _wall_line('x', wz1, wx0, wx1, [])
                    built_edges.add(('N', wz1))
            else:
                gap = [(rcx - 2, rcx + 2)] if partner else []
                _wall_line('x', wz1, wx0, wx1, gap)
                built_edges.add(('N', wz1))
                if partner:
                    door_specs.append((rcx, wz1, 'x'))
            if ('S', wz0) not in built_edges:
                _wall_line('x', wz0, wx0, wx1, [])
                built_edges.add(('S', wz0))
            # 东西侧墙（非门侧）
            if west:
                _wall_line('z', wx1, wz0, wz1, [])
            else:
                _wall_line('z', wx0, wz0, wz1, [])
            # 承重断柱（规格一.3：门对侧角落）
            self._lab_block(wx1 - 1.6 if west else wx0 + 1.6,
                            wz0 + 1.6, 2.0, 0.6)
        for (dx, dz, dax) in door_specs:
            LabDoor(dx, dz, 4.0, dax)            # 10 主门 + 2 互通门 = 12 扇

        # ================= 楼梯 / 竖井 / 主控门（动态定位） =================
        def _find_vrun(zlo, zhi, length, avoid):
            """找竖向直走廊（length 连格），避开 avoid 点位（有界，无死循环）"""
            for z in range(zlo, zhi):
                for x in range(1, 29):
                    if not all(self.is_floor((x, z + k))
                               for k in range(length)):
                        continue
                    if any(abs(x - ax) + abs(z + k - az) <= 3
                           for (ax, az) in avoid for k in range(length)):
                        continue
                    return (x, z)
            return None

        _avoid = []
        _stA = _find_vrun(17, 27, 2, _avoid) or (15, 20)
        _avoid.append(_stA)
        _stB = _find_vrun(3, 10, 2, _avoid) or (5, 5)
        _avoid.append(_stB)
        _shaft = _find_vrun(8, 14, 3, _avoid) or (10, 10)
        _avoid.append(_shaft)
        a_w = self.tile_to_world(_stA)           # 楼梯 A（南带，沿 +z）
        b_w = self.tile_to_world(_stB)           # 楼梯 B（北带，沿 +z）
        s_w = self.tile_to_world(_shaft)         # 竖井（中带，沿 +z 下行）
        Stairs(a_w.x, a_w.z, 0.0, 6.0, 6.0, 2.4, '+z', 12)
        Stairs(b_w.x, b_w.z, 0.0, 6.0, 6.0, 2.4, '+z', 12)
        # ---- 主控门：最靠南边的走廊格（迷宫深处尽头的死路感）----
        _md = min(self.floor_tiles, key=lambda t: (t[1], abs(t[0] - 15)))
        _mdw = self.tile_to_world(_md)
        MainDoor(_mdw.x, _mdw.z - 1.9)           # 贴南侧墙立方

        # ================= 2F：全幅楼板 + 同构迷宫矮墙（Y=6） =================
        build_slab_with_holes(
            -60.0, 60.0, -60.0, 60.0,
            [(a_w.x - 1.7, a_w.x + 1.7, a_w.z + 5.0, a_w.z + 6.0),
             (b_w.x - 1.7, b_w.x + 1.7, b_w.z + 5.0, b_w.z + 6.0)],
            6.0, thick=1.0)
        # 2F POI：出生点 / 日记（远离楼梯的走廊格）
        def _far_tile(avoid, min_d=8):
            best, bd = None, -1
            for t in self.floor_tiles:
                w = self.tile_to_world(t)
                d = min(dist_xz(w, av) for av in avoid)
                if d > bd and d >= min_d:
                    bd, best = d, t
            return best or self.floor_tiles[len(self.floor_tiles) // 2]
        _p2_spawn = _far_tile([Vec3(a_w.x, 0, a_w.z), Vec3(b_w.x, 0, b_w.z),
                               Vec3(_mdw.x, 0, _mdw.z)])
        _p2_diary = _far_tile([Vec3(a_w.x, 0, a_w.z), Vec3(b_w.x, 0, b_w.z),
                               self.tile_to_world(_p2_spawn)])
        _p2s_w = self.tile_to_world(_p2_spawn)
        _p2d_w = self.tile_to_world(_p2_diary)
        _protect2 = [Vec3(a_w.x, 6, a_w.z + 6), Vec3(b_w.x, 6, b_w.z + 6),
                     Vec3(_p2s_w.x, 6, _p2s_w.z), Vec3(_p2d_w.x, 6, _p2d_w.z)]
        for _z in range(self.grid_n):
            for _x in range(self.grid_n):
                if self.grid[_z][_x] != 1:
                    continue
                _w = self.tile_to_world((_x, _z))
                if any(dist_xz(Vec3(_w.x, 0, _w.z), _pp) < 7.0
                       for _pp in _protect2):
                    continue
                self._lab_block(_w.x, _w.z, 4.0, 4.0, cy=7.2, sy=2.4)

        # ================= 地下室（平移到竖井正下方，结构照旧） =================
        BASE_Y = -5.0
        sx, sz = s_w.x, s_w.z
        self._lab_block(sx - 2.2, sz + 4.0, 0.4, 9.6, cy=-2.4, sy=5.4)
        self._lab_block(sx + 2.2, sz + 4.0, 0.4, 9.6, cy=-2.4, sy=5.4)
        Stairs(sx, sz, 0.0, -5.0, 8.0, 2.4, '+z', 10)
        build_platform(sx, sz + 8.0, BASE_Y, 24.0, 24.0)
        self._lab_block(sx, sz - 4.0, 24.4, 0.6, cy=-3.0, sy=4.0)
        self._lab_block(sx, sz + 20.0, 24.4, 0.6, cy=-3.0, sy=4.0)
        self._lab_block(sx - 12.0, sz + 8.0, 0.6, 24.4, cy=-3.0, sy=4.0)
        self._lab_block(sx + 12.0, sz + 8.0, 0.6, 24.4, cy=-3.0, sy=4.0)
        self._lab_block(sx, sz + 1.0, 0.6, 10.0, cy=-3.0, sy=4.0)
        self._lab_block(sx + 6.0, sz + 2.0, 24.4, 0.6, cy=-3.0, sy=4.0)
        GlassTank(sx - 9.0, sz + 13.0, base_y=BASE_Y)
        GlassTank(sx + 3.0, sz + 16.0, base_y=BASE_Y)
        Keycard(sx + 9.5, sz + 16.0, base_y=BASE_Y)

        # ================= 内容布点（房间相对坐标 + 走廊动态选点） =================
        rc = {nm: (lambda b: ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2))(
            _room_bounds(r)) for nm, r in rooms.items()}
        # 手术台 ×3（互斥注册表语义保持：台房无罐，罐只在地下室）
        OperatingTable(rc['morgue'][0] - 1.5, rc['morgue'][1])
        OperatingTable(rc['surgery'][0], rc['surgery'][1])
        OperatingTable(rc['monitor'][0], rc['monitor'][1])
        for _tb in list(TABLES):
            spawn_blood_stain(_tb.x + random.uniform(-1.2, 1.2),
                              _tb.z + random.uniform(-1.2, 1.2))
        # 抽屉 ×6（规格：真实实例化入房，按 E 搜查 30% 掉落）
        Drawer(rc['morgue'][0] - 3.5, rc['morgue'][1] - 2.0)
        Drawer(rc['morgue'][0] + 3.2, rc['morgue'][1] - 2.0, ry=90)
        Drawer(rc['surgery'][0] + 3.5, rc['surgery'][1] - 2.0, ry=90)
        Drawer(rc['monitor'][0] - 3.5, rc['monitor'][1] - 2.0)
        Drawer(rc['monitor'][0] + 3.5, rc['monitor'][1] - 2.0, ry=90)
        Drawer(rc['storage'][0], rc['storage'][1])
        # 日记 ×5（停尸房/档案室/走廊×2/2F）——手术室改为纯布景房
        _corridor_pool = [t for t in self.floor_tiles
                          if not any(r[0] <= t[0] < r[0] + r[2]
                                     and r[1] <= t[1] < r[1] + r[3]
                                     for r in rooms.values())]
        _cd = random.choice(_corridor_pool)
        _cd2 = random.choice([t for t in _corridor_pool
                              if t != _cd] or [_cd])
        _cdw = self.tile_to_world(_cd)
        _cd2w = self.tile_to_world(_cd2)
        l3d_spots = [(rc['morgue'][0] + 2.5, 0.0, rc['morgue'][1] + 1.5),
                     (rc['archive'][0], 0.0, rc['archive'][1]),
                     (_cdw.x, 0.0, _cdw.z),
                     (_cd2w.x, 0.0, _cd2w.z),
                     (_p2d_w.x, 6.0, _p2d_w.z)]
        for (dx, dy, dz) in l3d_spots:
            _fid, _ftxt = next_fragment()
            DIARIES.append(Diary(Vec3(dx, dy, dz), _ftxt, frag_id=_fid,
                                 glow_rgb=(220, 190, 130)))
        # ---- ★ 规格二：布景房道具（纯装饰拼凑，极暗材质）----
        def _dk(a, b=8):
            return color.rgb(a, a, b)
        def _prop_sink(x, z):                    # 卫生间：洗手台
            Entity(model='cube', position=(x, 0.45, z), scale=(1.6, 0.9, 0.7),
                   color=_dk(16))
            Entity(model='cube', position=(x, 0.95, z - 0.2), scale=(1.2, 0.15, 0.4),
                   color=_dk(20))
        def _prop_cart(x, z):                    # 杂物间：倒塌的推拉车
            Entity(model='cube', position=(x, 0.35, z), scale=(1.4, 0.5, 0.8),
                   rotation_z=22, color=_dk(15))
            Entity(model='cube', position=(x + 0.9, 0.2, z + 0.3), scale=(0.6, 0.4, 0.5),
                   rotation_z=-14, color=_dk(13))
        def _prop_boxes(x, z):                   # 散落纸箱 ×3
            for _ox, _oz, _ry in ((-1.2, 0.4, 15), (0.6, -0.8, -25), (1.4, 0.9, 40)):
                Entity(model='cube', position=(x + _ox, 0.22, z + _oz),
                       scale=(0.55, 0.45, 0.55), rotation_y=_ry, color=_dk(18))
        def _prop_bed(x, z, broken=True):        # 病床（破损=倾斜）
            Entity(model='cube', position=(x, 0.3, z), scale=(0.9, 0.25, 2.0),
                   rotation_z=(7 if broken else 0), color=_dk(14))
            Entity(model='cube', position=(x, 0.55, z + 0.2), scale=(0.8, 0.18, 1.7),
                   rotation_z=(7 if broken else 0), color=_dk(22))
            Entity(model='cube', position=(x - 0.25, 0.75, z - 0.7),
                   scale=(0.5, 0.12, 0.3), color=_dk(19))
        _prop_sink(rc['bath'][0], rc['bath'][1])
        _prop_cart(rc['junk'][0], rc['junk'][1])
        _prop_boxes(rc['power'][0], rc['power'][1])
        _prop_bed(rc['ward'][0], rc['ward'][1], broken=True)
        _prop_bed(rc['duty'][0], rc['duty'][1], broken=False)
        # ---- 布景房随机角落血迹 + 病房血迹簇 ----
        for nm in ('ward', 'bath', 'junk', 'duty'):
            if nm == 'ward' or random.random() < 0.5:
                spawn_blood_stain(rc[nm][0] + random.uniform(-3, 3),
                                  rc[nm][1] + random.uniform(-2, 2))
        # ---- ★ 规格二.3：房内柜子 60% 概率（门对侧角落）----
        for nm, r in rooms.items():
            if random.random() < 0.6:
                _cb = _room_bounds(r)
                CABINETS.append(Cabinet(Vec3(
                    rc[nm][0] + (_cb[1] - rc[nm][0] - 1.2
                                 if r[0] + r[2] / 2 > 15 else -3.4),
                    0, rc[nm][1] - 2.2)))   # ★ Cabinet 不自注册——显式入列
        # ---- ★ 规格二.3：长走廊固定 3 个逃生柜（彼此远离）----
        _cab_spots = []
        _cab_pool = [t for t in _corridor_pool
                     if dist_xz(self.tile_to_world(t),
                                Vec3(_mdw.x, 0, _mdw.z)) > 8.0]
        random.shuffle(_cab_pool)
        for t in _cab_pool:
            _tw = self.tile_to_world(t)
            if all(dist_xz(_tw, Vec3(c.x, 0, c.z)) > 18.0 for c in _cab_spots):
                _cab_spots.append(Vec3(_tw.x, 0, _tw.z))
            if len(_cab_spots) >= 3:
                break
        for _cp in _cab_spots:
            CABINETS.append(Cabinet(_cp))    # ★ 走廊逃生柜显式入列
        # 报告 ×5（停尸房/监控室/走廊/地下室 ×2）
        for (_rx, _rz, _rb) in ((rc['morgue'][0] - 3.0, rc['morgue'][1] + 2.0, 0.0),
                                (rc['monitor'][0] + 2.5, rc['monitor'][1] + 1.5, 0.0),
                                (_cdw.x + 3.0, _cdw.z, 0.0),
                                (sx - 7.0, sz + 2.0, -5.0),
                                (sx + 6.0, sz + 12.0, -5.0)):
            _fid, _ftxt = next_fragment()
            LabReport(_rx, _rz, base_y=_rb, text=_ftxt, frag_id=_fid)

        # ================= 走廊布景（动态选点，避开出生/楼梯/门） =================
        _room_tiles = set()
        for (rx, rz, rw, rh) in rooms.values():
            for _x in range(rx, rx + rw):
                for _z in range(rz, rz + rh):
                    _room_tiles.add((_x, _z))
        _scenic = [t for t in self.floor_tiles
                   if t not in _room_tiles
                   and dist_xz(self.tile_to_world(t), Vec3(_mdw.x, 0, _mdw.z)) > 6.0
                   and dist_xz(self.tile_to_world(t), Vec3(a_w.x, 0, a_w.z)) > 4.0
                   and dist_xz(self.tile_to_world(t), Vec3(b_w.x, 0, b_w.z)) > 4.0
                   and dist_xz(self.tile_to_world(t), Vec3(sx, 0, sz)) > 4.0]
        random.shuffle(_scenic)
        _pick = _scenic[:]
        def _next_spot():
            return self.tile_to_world(_pick.pop()) if _pick else \
                self.tile_to_world(random.choice(self.floor_tiles))
        for _ in range(3):                       # 滴水管道 ×3（含 3D 声源）
            _s = _next_spot()
            DripPipe(_s.x, _s.z)
        _e1, _e2 = _next_spot(), _next_spot()    # 配电箱 ×2
        ElecBox(_e1.x, _e1.z, ry=90.0)
        ElecBox(_e2.x, _e2.z, ry=-90.0)
        for _ in range(3):                       # 应急灯 ×3
            _s = _next_spot()
            WarningLight(_s.x, _s.z)
        for _ in range(6):                       # 白丝 ×6（走廊宽 4 米，1.5 宽必可绕行）
            _s = _next_spot()
            SpiderWeb(Vec3(_s.x, 0, _s.z), rotation_y=90)
        _m1, _m2 = _next_spot(), _next_spot()    # 破镜 ×2
        BrokenMirror(_m1.x, _m1.z, 90)
        BrokenMirror(_m2.x, _m2.z, 90)
        for _ in range(4):                       # 乌鸦 ×4
            _s = _next_spot()
            CROWS.append(Crow(Vec3(_s.x, 0, _s.z)))

        # ================= 环境音 / 开阔点 / 出生点 / 怪物 =================
        AmbientSound3D(Vec3(rc['monitor'][0], 1.5, rc['monitor'][1]),
                       'clock_tick', base_volume=0.9, hear_range=9.0)
        AmbientSound3D(Vec3(rc['morgue'][0] - 3.5, 1.5, rc['morgue'][1] - 2.5),
                       'water_drip', base_volume=0.85, hear_range=11.0)
        self.open_points = [self.tile_to_world(t) for t in self.floor_tiles]
        self.open_points += [Vec3(_p2s_w.x, 6.0, _p2s_w.z),
                             Vec3(a_w.x, 6.0, a_w.z + 6.0),
                             Vec3(b_w.x, 6.0, b_w.z + 6.0)]
        # 玩家：最北端走廊格，面朝南（迷宫深处）
        _ps = max(self.floor_tiles, key=lambda t: (t[1], abs(t[0] - 15)))
        _psw = self.tile_to_world(_ps)
        self.player = Player(Vec3(_psw.x, 0, _psw.z), 0)
        player = self.player
        # 出生点：1F ×3（BFS 距玩家分散）+ 2F ×1 + 地下室 ×1
        _dists = self.bfs_distances(_ps)
        _sp1 = sorted([t for t in self.floor_tiles if _dists.get(t, 0) >= 12],
                      key=lambda t: -_dists.get(t, 0))
        for t in (_sp1[:1] + _sp1[len(_sp1) // 2:len(_sp1) // 2 + 1]
                  + _sp1[-1:]):
            _sw = self.tile_to_world(t)
            spawn_points.append(Vec3(_sw.x, 0, _sw.z))
        spawn_points.extend([Vec3(_p2s_w.x, 6.0, _p2s_w.z),
                             Vec3(sx, BASE_Y, sz + 16.0)])
        # 怪物：聆听者 1F（远离玩家 ≥12 步）+ 盲蛛 2F 迷宫
        _mt = _sp1[0] if _sp1 else _ps
        _mw = self.tile_to_world(_mt)
        MONSTERS.append(Monster(None, world_pos=Vec3(_mw.x, 0, _mw.z)))
        MONSTERS.append(Crawler(world_pos=Vec3(_p2s_w.x, 6.0, _p2s_w.z)))
        print('=' * 56)
        print('  第三关 · 核心实验室（30×30 迷宫骨架 120×120 米）')
        print('  五个房间藏在迷宫角落——相邻房间有互通门，可绕环形路线')
        print(f'  主控门在迷宫最南端 ({_mdw.x:.0f},{_mdw.z:.0f})；门禁卡在地下室')
        print('  手术台/抽屉/培养罐可搜查——30% 翻出实验报告')
        print(f'  生命 ×{get_start_lives()} | 残缺实验报告藏着这座研究所的真相')
        if active_modifier:
            print(f'  本局词条【{active_modifier["name"]}】：{active_modifier["desc"]}')
        print('=' * 56)

    def _load_level_1(self):
        """第一关「潮湿回廊」：40x40 DFS 迷宫；3 保险丝 + 1 出口；
        2 只聆听者 + 3 根盲蛛丝 + 4 只乌鸦 + 3 台伪声呐。"""
        self.grid_n = GRID_L1
        self.grid = generate_maze_grid(GRID_L1)
        self._collect_tiles()
        self._build_geometry()
        dists = self.bfs_distances(self.spawn_tile)
        used = {self.spawn_tile}

        # ---- 出口：最远死胡同之一 ----
        far_dead = sorted(self.dead_ends, key=lambda t: -dists.get(t, 0))
        exit_tile = random.choice(far_dead[:3]) if far_dead else self.random_floor_tile()
        used.add(exit_tile)
        self.exit_gates = [ExitGate(self.tile_to_world(exit_tile), is_real=True)]

        # ---- 3 保险丝：远处死胡同 ----
        fuse_pool = [t for t in self.dead_ends if dists.get(t, 0) >= 8 and t not in used]
        for t in self._pick_spread_tiles(fuse_pool, FUSES_NEEDED, 8, used):
            FUSES.append(Fuse(self.tile_to_world(t)))

        # ---- 怪物生态 ----
        self._spawn_ecology(dists, used, listener_count=1, web_count=WEB_COUNT,
                            crow_count=0, sonar_count=3, crawler_count=0)

        sp_tiles = self._pick_spread_tiles(self.floor_tiles[:], 4, 10, used)  # ★ 避开白丝
        spawn_points.extend([self.tile_to_world(t) for t in sp_tiles])
        # ---- 玩家 ----
        self._spawn_player()
        # ★ 规格三：盲女失忆开场（第一关进入时浮起这段独白）
        _show_amnesia_intro()
        print(_AMNESIA_INTRO.replace(chr(10), ' '))
        print('=' * 56)
        print('  第一关 · 潮湿回廊（40x40 DFS 大迷宫）')
        print(f'  生命 ×{get_start_lives()} | 保险丝 {FUSES_NEEDED} 枚')
        if active_modifier:
            print(f'  本局词条【{active_modifier["name"]}】：{active_modifier["desc"]}')
        print('  保持安静……它在听。')
        print('=' * 56)

    def _load_level_2(self):
        """第二关「立体双层结构」：
        1F（Y=0）：DFS 迷宫（出口 + 保险丝 + 怪物 + 柜子/管子）
        2F（Y=6）：高台阁楼（build_platform 架空平台 + 围壁），玩家出生在 2F。
        上行楼梯连接 1F↔2F，怪物经楼梯 y 适配追踪玩家。
        3 本蓝色日记分布在两层。"""
        self.grid_n = GRID_L2
        self.grid = generate_maze_grid(GRID_L2)
        self._collect_tiles()
        self._build_geometry()
        dists = self.bfs_distances(self.spawn_tile)
        used = {self.spawn_tile}

        # ---- ★ 全尺寸 2F（规格三.1）：与 1F 迷宫同范围的 Y=6 整层楼板 ----
        # 楼板（厚 1 米，底面 Y=5，恰好悬在 4 米高迷宫墙之上）+ 四周护栏；
        # 两个【对角线位置】的上行楼梯洞口（西北 / 东南），二楼绝无死胡同死角。
        loft_cx, loft_cz = -20.0, -20.0       # 2F 出生锚点（沿用原阁楼中心）
        w0 = self.tile_to_world((0, 0))
        w1 = self.tile_to_world((self.grid_n - 1, self.grid_n - 1))
        b_lo = min(w0.x, w1.x) - 2.0          # 楼板外沿（覆盖外墙厚度）
        b_hi = max(w0.x, w1.x) + 2.0
        # ---- ★ L2 专属布景（规格一.1）：滴水管道 + 漏电电线 + 3D 音效
        # （第二关不生成手术台/培养罐——那些属于第三关实验室）----
        DripPipe(loft_cx + 20.0, loft_cz + 8.0)             # 1F 中部上空管道（x=0）
        DripPipe(0.0, 20.0)                                  # ★ 挪离东南楼梯象限（x>15,z>15）
        ElecBox(b_lo + 3.0, b_lo + 4.0, ry=90.0)            # 1F 外墙配电箱
        ElecBox(b_hi - 4.0, b_hi - 6.0, ry=-90.0)
        sp2 = (Vec3(loft_cx + 3, 6, loft_cz - 3), Vec3(loft_cx - 3, 6, loft_cz + 3))

        def _stair_tile(cond):
            """楼梯基座：沿 +z 有 3 连通地板、位于指定象限、远离 2F 出生点"""
            pool = [t for t in self.floor_tiles
                    if all(self.is_floor((t[0], t[1] + k)) for k in (1, 2))
                    and cond(self.tile_to_world(t))
                    and all(dist_xz(self.tile_to_world(t), s) > 12.0 for s in sp2)
                    and t not in used]
            random.shuffle(pool)
            return pool[0] if pool else None

        t_a = _stair_tile(lambda w: w.x < -15 and w.z < -15)     # 楼梯 A：西北象限
        t_b = _stair_tile(lambda w: w.x > 15 and w.z > 15)       # 楼梯 B：东南象限
        if t_a is None:
            t_a = random.choice(self.floor_tiles)
        if t_b is None:
            t_b = random.choice(self.floor_tiles)
        used.add(t_a)
        used.add(t_b)
        wa, wb = self.tile_to_world(t_a), self.tile_to_world(t_b)
        # 楼梯 A / B：1F（Y=0）→ 2F（Y=6），12 级台阶（0.5 米/级，步高容差内）
        Stairs(wa.x, wa.z, 0.0, 6.0, 6.0, 2.4, '+z', 12)
        Stairs(wb.x, wb.z, 0.0, 6.0, 6.0, 2.4, '+z', 12)
        # 楼板掏洞：洞口对准楼梯上段（玩家头部穿楼板处 + 出洞走道）
        # ★ 洞口精确止于楼梯顶端（楼梯上段穿过楼板带，玩家出洞即踏上楼板，绝不坠落）
        holes2 = [(wa.x - 1.7, wa.x + 1.7, wa.z + 3.2, wa.z + 6.0),
                  (wb.x - 1.7, wb.x + 1.7, wb.z + 3.2, wb.z + 6.0)]
        build_slab_with_holes(b_lo, b_hi, b_lo, b_hi, holes2, 6.0, thick=1.0)
        # 2F 四周护栏（y 6~7，防坠落）
        span = b_hi - b_lo + 0.6
        self._lab_block(0.0, b_hi - 0.3, span, 0.6, cy=6.5, sy=1.0)
        self._lab_block(0.0, b_lo + 0.3, span, 0.6, cy=6.5, sy=1.0)
        self._lab_block(b_hi - 0.3, 0.0, 0.6, span, cy=6.5, sy=1.0)
        self._lab_block(b_lo + 0.3, 0.0, 0.6, span, cy=6.5, sy=1.0)
        # ---- ★ 2F 迷宫墙（规格一.1）：1F 网格墙在 Y=6~10 整层复制——
        # 二楼不再是空旷平台，结构与一楼一致；楼梯出洞口周边 7 米留空不堵人 ----
        _stair_tops = (Vec3(wa.x, 0, wa.z + 6.0), Vec3(wb.x, 0, wb.z + 6.0))
        for _gx in range(self.grid_n):
            for _gz in range(self.grid_n):
                if self.is_floor((_gx, _gz)):
                    continue
                _w2 = self.tile_to_world((_gx, _gz))
                if any(dist_xz(_w2, _s) < 7.0 for _s in _stair_tops):
                    continue
                self._lab_block(_w2.x, _w2.z, 4.0, 4.0,
                                cy=6.0 + WALL_HEIGHT / 2, sy=WALL_HEIGHT)
        # ---- ★ 2F 日记 ×2 + 出生点 ×2（规格一.1：二楼有日记与逃生点）----
        _f2_pool = [t for t in self.floor_tiles
                    if all(dist_xz(self.tile_to_world(t), _s) > 10.0
                           for _s in _stair_tops) and t not in used]
        _f2_spots = self._pick_spread_tiles(_f2_pool, 5, 12, used)   # ★ 2 日记 + 3 出生点
        used.update(_f2_spots)
        for _i, _t in enumerate(_f2_spots):
            _w2 = self.tile_to_world(_t)
            if _i < 2:
                _fid, _ftxt = next_fragment()
                DIARIES.append(Diary(Vec3(_w2.x, 6.0, _w2.z), _ftxt, frag_id=_fid,
                                     glow_rgb=(80, 120, 255)))
            else:
                spawn_points.append(Vec3(_w2.x, 6.0, _w2.z))

        # ---- 出口：1F 迷宫中最远死胡同（三个，一个真实）----
        far_dead = sorted(self.dead_ends, key=lambda t: -dists.get(t, 0))
        exit_tiles = self._pick_spread_tiles([t for t in far_dead
                                             if t not in used], 3, 10, used)
        real_idx = random.randrange(len(exit_tiles))
        self.exit_gates = []
        for i, t in enumerate(exit_tiles):
            if i == real_idx:
                ep = self.tile_to_world(t)
                self.exit_gates.append(ExitGate(Vec3(ep.x, 2.5, ep.z), is_real=True))
            else:
                self.exit_gates.append(ExitGate(self.tile_to_world(t), is_real=False))

        # ---- 3 保险丝（1F 迷宫内）----
        fuse_pool = [t for t in self.dead_ends if dists.get(t, 0) >= 6 and t not in used]
        for t in self._pick_spread_tiles(fuse_pool, FUSES_NEEDED, 7, used):
            FUSES.append(Fuse(self.tile_to_world(t)))

        # ---- ★ 6 本蓝色日记：2F ×2（见上方 f2_spots）+ 1F ×4 ----
        diary_pool = [t for t in self.floor_tiles
                      if dists.get(t, 0) >= 4 and t not in used]
        for t in self._pick_spread_tiles(diary_pool, 4, 5, used):
            _fid, _ftxt = next_fragment()
            DIARIES.append(Diary(self.tile_to_world(t), _ftxt, frag_id=_fid,
                                 glow_rgb=(80, 120, 255)))

        # ---- 柜子 + 空管子（1F 迷宫内）----
        cab_pool = [t for t in self.floor_tiles if dists.get(t, 0) >= 6 and t not in used]
        for t in self._pick_spread_tiles(cab_pool, 4, 10, used):
            yaw = 0
            for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
                if self.is_floor((t[0] + dx, t[1] + dz)):
                    yaw = math.degrees(math.atan2(dx, -dz))   # 柜门朝开放方向
                    break
            w = self.tile_to_world(t)
            CABINETS.append(Cabinet(Vec3(w.x, 0, w.z), rotation_y=yaw))
        pipe_pool = [t for t in self.floor_tiles if t not in used]
        for t in self._pick_spread_tiles(pipe_pool, 3, 9, used):
            PIPES.append(PipeItem(self.tile_to_world(t)))

        # ---- 怪物生态（更凶险）----
        self._spawn_ecology(dists, used, listener_count=1, web_count=WEB_COUNT,
                            crow_count=0, sonar_count=4, crawler_count=1)

        # ---- ★ 多层地形：出生高台 + 出口高台 + 两段楼梯 ----
        sp_1f = self._pick_spread_tiles(self.floor_tiles[:], 3, 10, used)  # ★ 避开白丝
        spawn_points.extend([self.tile_to_world(t) for t in sp_1f])  # 1F 出生点 ×3（规格五）
        # ★ 2F 逃生点 ×2 已由 f2_spots 分布在二楼迷宫地板上（共 5 点）
        # ---- ★ 玩家出生在 2F 阁楼上（Y=6）----
        self._spawn_player()
        player.position = Vec3(loft_cx, 6.0, loft_cz)
        player.spawn_position = Vec3(loft_cx, 6.0, loft_cz)
        player.y = 6.0
        print('=' * 56)
        print('  第二关 · 立体双层迷宫（1F 地面 + 2F 阁楼 Y=6）')
        print('  出生在 2F 阁楼——找到下行楼梯到 1F 迷宫')
        print('  出口和保险丝在 1F；蓝色日记分布在两层')
        print(f'  生命 ×{get_start_lives()} | 保险丝 {FUSES_NEEDED} 枚')
        if active_modifier:
            print(f'  本局词条【{active_modifier["name"]}】：{active_modifier["desc"]}')
        print('  ……这里的黑暗，更浓。')
        print('=' * 56)

    # ---------------- 放置辅助 ----------------
    def _collect_tiles(self):
        self.floor_tiles = [(x, z) for z in range(self.grid_n)
                            for x in range(self.grid_n) if self.grid[z][x] == 0]
        self.dead_ends = []
        for (x, z) in self.floor_tiles:
            if x % 2 == 1 and z % 2 == 1:
                if sum(1 for _ in self._neighbors((x, z))) == 1:
                    self.dead_ends.append((x, z))

    def _spawn_ecology(self, dists, used, listener_count, web_count,
                       crow_count, sonar_count, crawler_count=0):
        """放置怪物生态（规格二 分级）：聆听者 / ★盲蛛实体怪 / 白丝陷阱 / 乌鸦 / 伪声呐"""
        # ---- 聆听者主怪 ----
        if listener_count > 0:
            far = [t for t in self.floor_tiles
                   if dists.get(t, 0) >= 10 and t not in used]
            for t in self._pick_spread_tiles(far, listener_count, 8, used):
                MONSTERS.append(Monster(t))
        # ---- ★ 盲蛛实体怪（规格二.3）：对半分层——盲蛛放 2F（y=6），
        #      聆听者留 1F——开局两层各有威胁 ----
        if crawler_count > 0:
            crawl_pool = [t for t in self.floor_tiles
                          if dists.get(t, 0) >= 6 and t not in used]
            for t in self._pick_spread_tiles(crawl_pool, crawler_count, 10, used):
                _cw = self.tile_to_world(t)
                MONSTERS.append(Crawler(world_pos=Vec3(_cw.x, 6.0, _cw.z)))
        # ★ 白丝陷阱（盲蛛重构）：同样优先"走廊过道"（左右为墙的地板），
        #   但白丝宽度只有 1.5 米（约半条路）——绝不封死通道，玩家可绕行
        corridor = []
        for (x, z) in self.floor_tiles:
            if (x, z) in used:
                continue
            left_wall = not self.is_floor((x - 1, z))
            right_wall = not self.is_floor((x + 1, z))
            if left_wall and right_wall:             # 南北向走廊 → 白丝沿 X 铺设
                corridor.append((x, z, 0))
            elif (not self.is_floor((x, z - 1))
                  and not self.is_floor((x, z + 1))):  # 东西向走廊
                corridor.append((x, z, 90))
        random.shuffle(corridor)
        placed = 0
        for (x, z, rot) in corridor:
            if placed >= web_count:
                break
            if (x, z) in used:
                continue
            used.add((x, z))
            SpiderWeb(self.tile_to_world((x, z)), rotation_y=rot)   # 构造器自登记
            placed += 1
        # 乌鸦 / 伪声呐：随机地板（离出生点至少 6 步）
        mid = [t for t in self.floor_tiles if dists.get(t, 0) >= 6 and t not in used]
        for t in self._pick_spread_tiles(mid, crow_count, 5, used):
            CROWS.append(Crow(self.tile_to_world(t)))
        for t in self._pick_spread_tiles(mid, sonar_count, 7, used):
            SONARS.append(FakeSonar(self.tile_to_world(t)))

    def _spawn_player(self):
        """生成玩家：出生点高度取脚下地形（第二关出生在高台上）"""
        global player
        yaw = 0
        for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if self.is_floor((self.spawn_tile[0] + dx, self.spawn_tile[1] + dz)):
                yaw = math.degrees(math.atan2(dx, -dz))
                break
        pos = self.tile_to_world(self.spawn_tile)
        self.player = Player(pos, yaw)
        gy = get_ground_height(self.player.x, self.player.z, 6.0)
        self.player.y = gy                         # ★ 直接站上高台/地面
        self.player.spawn_position = Vec3(self.player.x, gy, self.player.z)
        player = self.player

    # ---------------- 场景销毁 ----------------
    def teardown(self):
        """★ 切换场景必调用：销毁一切实体并清空全部列表（含怪物 3D 音频与楼梯）"""
        global player, scare_active, scare_timer, monster_step_timer
        global buzz_timer, ambient_event_timer, danger_k, diary_open, spawn_points
        global current_round_fragments
        camera.parent = scene
        camera.position = Vec3(0, 16, -30)
        camera.rotation = Vec3(35, 0, 0)
        # ★ 先停掉每只怪物的 3D 循环喘息音（此时列表尚未清空），防止音频残留
        for m in list(MONSTERS):
            try:
                if getattr(m, 'breath_aud', None) is not None:
                    m.breath_aud.stop()
            except Exception:
                pass
        # ★ 再停掉房间 3D 环境音（时钟滴答/水滴——防止关卡切换后残留）
        for amb in list(AMBIENT_SOUNDS3D):
            try:
                if getattr(amb, 'audio', None) is not None:
                    amb.audio.stop()
            except Exception:
                pass
        for lst in (ECHO_SPHERES, RIPPLES, STONES, FUSES, DIARIES, CABINETS, PIPES,
                    CROWS, SONARS, SPIDERS, WEBS, SPIDER_LEGS, MONSTERS, WALLS,
                    DRIP_PIPES, ELEC_BOXES,
                    RAMPS, PLATFORMS, DOORS, WARNING_LIGHTS, BLOODPOOLS, MIRRORS,
                    TANKS, TABLES, DRAWERS, REPORTS, KEYCARDS, MAIN_DOORS,
                    AMBIENT_SOUNDS3D, WALKABLES):
            for e in list(lst):                 # ★ 浅拷贝遍历再销毁（try-except 防野指针）
                e.is_dead = True
                try:
                    destroy(e)
                except Exception:
                    pass
            lst.clear()
        ECHO_FADE.clear()                     # ★ 回声登记队列随关卡清空
        for g in list(ECHO_GHOSTS):         # ★ 幽灵方块逐个销毁
            try:
                destroy(g)
            except Exception:
                pass
        ECHO_GHOSTS.clear()
        for target in [self.ground, self.player] + list(self.exit_gates):
            if target is not None:
                target.is_dead = True
                try:
                    destroy(target)
                except Exception:
                    pass
        self.exit_gates = []
        self.ground = None
        self.player = None
        player = None
        spawn_points.clear()                  # ★ 清空出生点（新关卡重新生成）
        current_round_fragments = 0           # ★ 规格二.1：单局碎片计数归零
        _round_used_ids.clear()               # ★ 本局碎片分配记录清空
        global thunder_timer, thunder_left, thunder_active
        thunder_timer = THUNDER_INTERVAL      # ★ 规格五：雷暴计时重置
        thunder_left = 0.0
        if thunder_active:
            thunder_active = False
            _thunder_set_ambient(False)       # 上一局的雷暴光复原
        scare_active = False
        scare_timer = 0.0
        monster_step_timer = 0.0
        buzz_timer = 0.0
        ambient_event_timer = random.uniform(6.0, 12.0)
        danger_k = 0.0
        diary_open = False


# =====================================================================================
#  九、小地图（左上角）：敲击时显示 1.5 秒，中央箭头实时绑定玩家朝向
# =====================================================================================
minimap_panel = None
minimap_cells = []
minimap_marks = {}
minimap_arrow = None
_minimap_token = [0]


def build_minimap():
    global minimap_panel, minimap_cells, minimap_marks, minimap_arrow
    minimap_panel = Entity(parent=camera.ui, model='quad',
                           color=color.rgba(12, 12, 16, 190),
                           scale=(MINIMAP_SIZE, MINIMAP_SIZE),
                           position=window.top_left + Vec2(0.22, -0.22), z=2.2)
    minimap_panel.enabled = False
    cell = MINIMAP_SIZE * TILE / (MINIMAP_VIEW * 2)
    minimap_cells = []
    for _ in range(MINIMAP_CELL_POOL):
        c = Entity(parent=minimap_panel, model='quad',
                   color=color.rgb(0, 200, 200), scale=(cell, cell, 1),
                   enabled=False)
        minimap_cells.append(c)
    minimap_marks = {}
    for kind, count, col, size in (
            ('fuse', FUSES_NEEDED + 2, color.rgb(255, 210, 70), 0.030),
            ('monster', 6, color.rgb(255, 60, 60), 0.036),
            ('diary', 6, color.rgb(230, 220, 190), 0.024)):
        minimap_marks[kind] = [Entity(parent=minimap_panel, model='quad',
                                      color=col, scale=(size, size, 1), enabled=False)
                               for _ in range(count)]
    try:
        arrow_mesh = Mesh(vertices=[Vec3(0, 1, 0), Vec3(-0.7, -0.6, 0),
                                    Vec3(0.7, -0.6, 0)], mode='triangle')
        minimap_arrow = Entity(parent=minimap_panel, model=arrow_mesh,
                               color=color.rgb(120, 255, 230), scale=0.055)
    except Exception:
        minimap_arrow = Entity(parent=minimap_panel, model='quad',
                               color=color.rgb(120, 255, 230), scale=(0.028, 0.045))
    minimap_arrow.position = (0, 0)


def refresh_minimap():
    _minimap_token[0] += 1
    token = _minimap_token[0]
    minimap_panel.enabled = True
    invoke(_hide_minimap, token, delay=1.5)
    if player is None:
        return
    half = MINIMAP_SIZE / 2.0
    sx = half / MINIMAP_VIEW
    idx = 0
    for wall in list(WALLS):
        if wall.is_dead or idx >= len(minimap_cells):
            continue
        dx = wall.x - player.x
        dz = wall.z - player.z
        if abs(dx) > MINIMAP_VIEW or abs(dz) > MINIMAP_VIEW:
            continue
        c = minimap_cells[idx]
        idx += 1
        c.enabled = True
        c.x = clamp(dx * sx, -half + 0.01, half - 0.01)
        c.y = clamp(-dz * sx, -half + 0.01, half - 0.01)
    for c in minimap_cells[idx:]:
        c.enabled = False
    # 亮点：保险丝（黄）/ 聆听者（红）/ 日记（米白）
    for kind, source_list in (('fuse', FUSES), ('monster', MONSTERS),
                              ('diary', DIARIES)):
        i = 0
        for obj in list(source_list):
            if getattr(obj, 'is_dead', False) or i >= len(minimap_marks[kind]):
                continue
            dx = obj.x - player.x
            dz = obj.z - player.z
            if math.hypot(dx, dz) > MINIMAP_MARK_RANGE:
                continue
            mark = minimap_marks[kind][i]
            i += 1
            mark.enabled = True
            mark.x = clamp(dx * sx, -half + 0.015, half - 0.015)
            mark.y = clamp(-dz * sx, -half + 0.015, half - 0.015)
        for mark in minimap_marks[kind][i:]:
            mark.enabled = False


def _hide_minimap(token):
    if token == _minimap_token[0]:
        minimap_panel.enabled = False


# =====================================================================================
#  十、视觉叠加层：晕影 / ★柜内窥视遮罩 / 日记弹窗 / 死亡黑白化与嘲讽
#  ★ UI 层级规范（修复"字体乱码/看不清"）：z 越小越靠前（前景）。
#    排序（后→前）：模糊 -0.30 < 灰白 -0.35 < 晕影 -0.45 < 红闪 -0.50
#    < 日记遮罩 -0.55 < 日记面板 -0.60 < 日记文字 -0.65
#    < 窥视黑幕 -0.70 < 柜内提示 -0.75 < 嘲讽字幕 -0.80
# =====================================================================================
vignette_bars = []
vignette_intensity = 0.0
scare_flash = None
blur_overlay = None            # 词条·系统崩溃的灰雾
peek_bars = []                 # ★ 柜内窥视遮罩：四周纯黑，中间留竖缝+横缝
diary_panel = None             # 日记弹窗（单个 Text，自带 background）
diary_text = None
gray_overlay = None            # 死亡黑白化
taunt_text = None
cabinet_hint_text = None


def build_overlays():
    """构建全部全屏叠加层（晕影边条、红闪、★窥视遮罩、灰雾、日记弹窗、嘲讽字幕）"""
    global scare_flash, blur_overlay, diary_panel, diary_text
    global gray_overlay, taunt_text, cabinet_hint_text
    half_w = window.aspect_ratio * 0.5

    def _bar(w, h, x, y):
        e = Entity(parent=camera.ui, model='quad',
                   color=color.rgba(120, 0, 10, 0),
                   scale=(w, h), position=(x, y), z=2.6)
        vignette_bars.append(e)

    th_o, th_i = 0.085, 0.075
    _bar(3.2, th_o, 0.0, 0.5 - th_o / 2)
    _bar(3.2, th_i, 0.0, 0.5 - th_o - th_i / 2)
    _bar(3.2, th_o, 0.0, -0.5 + th_o / 2)
    _bar(3.2, th_i, 0.0, -0.5 + th_o + th_i / 2)
    _bar(th_o, 2.2, half_w - th_o / 2, 0.0)
    _bar(th_i, 2.2, half_w - th_o - th_i / 2, 0.0)
    _bar(th_o, 2.2, -half_w + th_o / 2, 0.0)
    _bar(th_i, 2.2, -half_w + th_o + th_i / 2, 0.0)
    # 突脸短促红闪
    scare_flash = Entity(parent=camera.ui, model='quad',
                         color=color.rgba(150, 0, 0, 0), scale=(3, 2), z=2.8)
    # ★ 柜内窥视遮罩（修复"柜子完全黑屏"）：屏幕四周纯黑，
    # 只在中间留一条竖直细缝 + 两道横向门板缝——"透过柜门缝隙往外看"
    slit_half = 0.085                          # 竖缝半宽（UI 单位）★ 加宽门缝视野（规格：必须能看到外面）
    aspect = window.aspect_ratio
    side_w = aspect / 2 - slit_half            # 左右黑板的宽度
    # 左右两块大黑板：把屏幕两侧完全压黑，只在中间留出竖直细缝
    for side in (-1, 1):
        e = Entity(parent=camera.ui, model='quad',
                   color=color.rgba(0, 0, 0, 255),
                   scale=(side_w, 2.4),
                   position=(side * (slit_half + side_w / 2), 0), z=3.0)
        peek_bars.append(e)
    # 两道横向门板缝（细黑条横过竖缝，木板门的横缝质感）
    for hy in (0.13, -0.13):
        e = Entity(parent=camera.ui, model='quad',
                   color=color.rgba(0, 0, 0, 255),
                   scale=(slit_half * 2 + 0.03, 0.035),
                   position=(0, hy), z=3.0)
        peek_bars.append(e)
    for e in peek_bars:
        e.enabled = False
    # 词条·系统崩溃：常驻灰雾（视野极度模糊的模拟）
    blur_overlay = Entity(parent=camera.ui, model='quad',
                          color=color.rgba(60, 60, 66, 0), scale=(3, 2), z=2.7)
    blur_overlay.enabled = False
    # 死亡黑白化：白闪 → 常驻灰白
    gray_overlay = Entity(parent=camera.ui, model='quad',
                          color=color.rgba(220, 220, 220, 0), scale=(3, 2), z=3.2)
    # ★ 日记弹窗（规格一.3 彻底重写）：弃用"遮罩+面板+多行文字"的拼凑结构
    #   （旧版 diary_mask 漏写 parent=camera.ui，黑遮罩飘进 3D 世界——半黑半白的根源）。
    #   改用单个 Text 的自带来背景：background=True + background_color，
    #   黑底白字自成一体、绝对挂载 camera.ui、绝不错位。
    #   wordwrap 限制行宽避免超出屏幕；z=3.5 位于晕影之上、顶级文字之下。
    diary_text = Text(parent=camera.ui, text='', position=(0, 0.05), origin=(0, 0),
                      scale=1, color=color.rgb(255, 250, 235), z=3.5,
                      background=True)
    diary_text.background.color = color.rgba(10, 10, 10, 240)   # 黑底
    diary_text.wordwrap = 24               # 每行约 24 个字，不超出屏幕
    diary_text.enabled = False
    diary_panel = (diary_text,)            # 保持旧接口：显隐元组只含一个实体
    # 死亡嘲讽字幕（英文台词，配合占位语音）
    taunt_text = Text(parent=camera.ui, text='', position=(0, 0.08), origin=(0, 0),
                      scale=1.2, color=color.rgb(255, 240, 240), z=5.0)
    taunt_text.enabled = False
    # 柜内提示（层级在窥视黑幕之前，保证可读）
    cabinet_hint_text = Text(parent=camera.ui,
                             text='藏在柜子里……透过门缝往外看（按 E 离开）',
                             position=(0, -0.34), origin=(0, 0), scale=1,
                             color=color.rgb(210, 210, 220), z=3.5)
    cabinet_hint_text.enabled = False


def set_peek_mask(on):
    """★ 开关柜内窥视遮罩（钻入/离开柜子时调用）"""
    for e in peek_bars:
        e.enabled = on
    cabinet_hint_text.enabled = on


def update_vignette(dt):
    global vignette_intensity
    target = danger_k
    vignette_intensity += (target - vignette_intensity) * min(dt * 3.5, 1.0)
    _exhaust_pulse[0] = max(0.0, _exhaust_pulse[0] - dt * 1.4)   # ★ 力竭脉冲衰减
    base = max(int(150 * vignette_intensity), int(110 * _exhaust_pulse[0]))
    if base > 0:
        for e in vignette_bars:
            e.color = color.rgba(120, 0, 10, base)
    else:
        for e in vignette_bars:
            e.color = color.rgba(120, 0, 10, 0)


def set_vignette_instant(intensity):
    global vignette_intensity
    vignette_intensity = intensity
    base = int(150 * intensity)
    for e in vignette_bars:
        e.color = color.rgba(120, 0, 10, max(0, base))


def reset_vignette():
    global vignette_intensity
    vignette_intensity = 0.0
    for e in vignette_bars:
        e.color = color.rgba(120, 0, 10, 0)
    if scare_flash is not None:
        scare_flash.color = color.rgba(150, 0, 0, 0)
    if gray_overlay is not None:
        gray_overlay.color = color.rgba(220, 220, 220, 0)
    if taunt_text is not None:
        taunt_text.enabled = False


def _scare_flash_step(alpha):
    if scare_flash is not None:
        scare_flash.color = color.rgba(150, 0, 0, alpha)


def _gray_step(alpha):
    """死亡黑白化的 invoke 步进：白闪 → 常驻灰白"""
    if gray_overlay is not None:
        gray_overlay.color = color.rgba(220, 220, 220, alpha)


def open_diary(text):
    """弹出阅读 UI（★ 规格一：游戏不暂停，怪物继续移动，BGM 降至 30%）。
    黑底白字单实体，parent=camera.ui，z=3.5。
    按 E / Esc 关闭，按 R 拾取（在 input 中分发）。"""
    global diary_open
    diary_open = True
    wrapped = '\n'.join(text[i:i + 22] for i in range(0, len(text), 22))
    diary_text.text = ('— 伊 芙 琳 —\n\n' + wrapped
                       + '\n\n· · ·\n[E] 关闭  [R] 拾取')
    for e in diary_panel:
        e.enabled = True
        try:                                    # ★ 规格三.2：0.3 秒淡入
            _full = e.color
            e.color = Color(_full[0], _full[1], _full[2], 0)
            e.animate_color(_full, duration=0.3)
        except Exception:
            pass
    apply_mouse_state()
    # ★ BGM 降至 30%（避免干扰倾听脚步声，规格一.3）
    try:
        if bgm_audio is not None:
            bgm_audio.volume = 0.32 * 0.3
    except Exception:
        pass


def _hide_diary_panel():
    """淡出动画结束后统一隐藏阅读面板"""
    for e in diary_panel:
        e.enabled = False


def close_diary():
    """关闭阅读 UI，恢复 BGM 音量"""
    global diary_open
    if not diary_open:
        return
    diary_open = False
    for e in diary_panel:
        try:                                    # ★ 规格三.2：0.3 秒淡出后隐藏
            _cur = e.color
            e.animate_color(Color(_cur[0], _cur[1], _cur[2], 0), duration=0.3)
        except Exception:
            e.enabled = False
    invoke(_hide_diary_panel, delay=0.32)
    apply_mouse_state()
    try:
        if bgm_audio is not None:
            bgm_audio.volume = 0.32    # 恢复正常 BGM 音量
    except Exception:
        pass


# =====================================================================================
#  十一、UI 构建（主菜单 / 关卡选择 / 技能树 / 设置 / HUD / 暂停 / 结算）
#  ★ 排版修复：所有面板文字 z 层级高于背景面板（更小的 z 在前景）；
#    背景统一深色半透明 rgba(20,20,20,200)；关卡名字号收敛（scale 1.0），
#    长描述拆成按钮下方的小字副标题，绝不溢出按钮框。
#  ★★ 规格二（本次修复，最高优先级）——鼠标可点击保障 + z 语义修正：
#    1. 所有 UI 一律 parent=camera.ui（各实体构造处已显式声明）。
#    2. ★ z 语义已按本机 Ursina 5.2 源码核实：camera.ui 渲染层
#       set_depth_test(0)——UI 靠绘制顺序决定覆盖，z 越大越后绘制、
#       越靠前（铁证：ursina 自身 overlay 用 z=-99 垫底）。因此层级表为：
#       背景板/遮罩 z=1.0（无碰撞体）→ 面板 z=1.5（无碰撞体）→
#       按钮 z=2.0 → 面板文字 z=2.5 → HUD/叠加层 2.6+ → 弹窗 3.4+ →
#       顶级文字 5.5+。与规格模板"bg z=1、btn z=2"完全一致。
#    3. 全部背景板/遮罩改为无碰撞体的纯 Entity（规格二.2"绝对不能带
#       collider"）——屏幕上不存在任何"隐形黑块"挡鼠标射线。
#    4. Ursina 的 Button 自带 collider='box'，点击由引擎鼠标射线处理。
# =====================================================================================
ui_groups = {}
_toast_token = [0]
_taunt_token = [0]      # 嘲讽字幕令牌（突脸 / GAME OVER 共用，防旧延迟误隐藏）
toast_text = None
death_text = None
win_text = None
status_text = None
echo_text = None
stamina_fill = None
model_warn_text = None       # ★ 模型缺失警告（屏幕中央红字）
o2_bg = None
o2_fill = None
o2_label = None
prompt_text = None
sens_value_text = None
menu_buttons = []


_AMNESIA_INTRO = ('我……是谁？\n我的眼睛为什么看不见？\n这里好黑，只有回音……')


def _show_amnesia_intro():
    """★ 规格三：盲女失忆开场（第一关进入时显示 6 秒）"""
    intro_text.text = _AMNESIA_INTRO
    intro_text.enabled = True
    invoke(_hide_amnesia_intro, delay=6.0)


def _hide_amnesia_intro():
    intro_text.enabled = False


def _add_to_group(name, *entities):
    ui_groups.setdefault(name, []).extend(entities)


def show_group(*names):
    hide_all_ui()
    for name in names:
        for e in ui_groups.get(name, []):
            e.enabled = True


def hide_all_ui():
    for entities in ui_groups.values():
        for e in entities:
            e.enabled = False


def show_toast(message):
    _toast_token[0] += 1
    toast_text.text = message
    toast_text.enabled = True
    invoke(_hide_toast, _toast_token[0], delay=2.2)


def _hide_toast(token):
    if token == _toast_token[0]:
        toast_text.enabled = False


def update_status_text():
    key_tag = ('   [门禁卡 ✓]'
               if (player is not None and getattr(player, 'has_keycard', False))
               else '')
    status_text.text = (f'生命 ×{player_lives}   保险丝：{collected_fuses}/{FUSES_NEEDED}'
                        f'   日记 ×{collected_diaries}{key_tag}'
                        + (f'   【{active_modifier["name"]}】' if active_modifier else ''))


def build_all_ui():
    global toast_text, death_text, win_text, status_text, echo_text
    global stamina_fill, o2_bg, o2_fill, o2_label, prompt_text
    global sens_value_text, fear_fill, fear_bg, fear_label
    # ★ 关键按钮/面板提为模块级全局（状态切换与自动化测试需要引用）
    global menu_title, btn_start, btn_archive, btn_settings, btn_quit
    global ls_title, ls_mask, lv1, st_mask, archive_rows, ar_mask
    global lr_title, lr_text, ar_stats, dev_btn, lr_mask, lr_close
    global menu_bg, st_back
    global set_mask, set_back, set_panel, sens_minus, sens_plus   # ★ 提为全局（自动化测试/状态切换引用）
    global ls_panel, st_panel
    toast_text = Text(parent=camera.ui, text='', position=(0, 0.42), origin=(0, 0),
                      scale=1, color=color.rgb(255, 210, 120), z=6.0)
    toast_text.enabled = False

    # ================= 主菜单（★ 按标准模板重写：字体两句 + 结构对齐）=================
    # 1. 背景板：深灰半透明 rgba(20,20,20,220)、全屏随宽、无碰撞体（不挡鼠标射线）。
    # 2. 标题/副标题：origin=(0,0) 居中锚点。
    # 3. 按钮：文字一律经 text= 传入（绝不手动加 Text 子实体），on_click 事后绑定。
    # ★ z 约定（像素实测终版）：camera.ui 中 z 越小越靠前（负数最前）。
    #   底板一律沉底（z=30），按钮/文字保持小值在前——修正历史误判。
    menu_bg = Entity(parent=camera.ui, model='quad',
                     color=color.rgba(20, 20, 20, 220),
                     scale=(window.aspect_ratio, 1), z=30)   # ★ 底板沉底（z 小者在前）
    menu_title = Text(parent=camera.ui, text='B L I N D   H O R R O R',
                      origin=(0, 0), y=0.3, scale=1.2, color=color.red, z=5)
    menu_sub = Text(parent=camera.ui, text='盲女伊芙琳 · 废弃研究所 · 暗夜回声',
                    origin=(0, 0), y=0.2, scale=1,
                    color=color.rgb(200, 200, 200), z=5)
    btn_start = Button(parent=camera.ui, text='开始游戏',
                       scale=(0.35, 0.08), y=0.05, z=5,
                       color=color.dark_gray, highlight_color=color.red)
    btn_start.on_click = open_level_select          # 绑定函数
    btn_archive = Button(parent=camera.ui, text='残存记忆（档案库）',
                         scale=(0.35, 0.08), y=-0.06, z=5,
                         color=color.dark_gray, highlight_color=color.red)
    btn_archive.on_click = open_archive
    btn_settings = Button(parent=camera.ui, text='设置',
                          scale=(0.35, 0.08), y=-0.17, z=5,
                          color=color.dark_gray, highlight_color=color.red)
    btn_settings.on_click = open_settings
    btn_quit = Button(parent=camera.ui, text='退出游戏',
                      scale=(0.35, 0.08), y=-0.28, z=5,
                      color=color.dark_gray, highlight_color=color.red)
    btn_quit.on_click = application.quit
    for b in (btn_start, btn_archive, btn_settings, btn_quit):
        b.text_entity.scale = 1               # 防御性归一（正确字体下即默认值）
        b.text_entity.color = color.rgb(255, 255, 255)
    menu_buttons.extend([btn_start, btn_archive, btn_settings, btn_quit])
    menu_help = Text(parent=camera.ui,
                     text='戴上耳机 · 右键敲击回声视物 · 左键潜行 + Q 屏息 · E 交互',
                     origin=(0, 0), y=-0.4, scale=1,
                     color=color.rgb(180, 180, 180), z=5)
    _add_to_group('menu', menu_bg, menu_title, menu_sub, btn_start, btn_archive,
                  btn_settings, btn_quit, menu_help)

    # ================= 关卡选择（★ 规格二：背景板/遮罩为无碰撞体 Entity，
    # z=1.0 垫底；按钮 z=2.0 在上可点击；文字 z=2.5）=================
    ls_mask = Entity(parent=camera.ui, model='quad',
                     color=color.rgba(20, 20, 20, 200),   # ★ 规格深灰半透明
                     scale=(window.aspect_ratio, 1), z=30)  # ★ 底板沉底
    ls_title = Text(parent=camera.ui, text='选 择 关 卡', position=(0, 0.27),
                    origin=(0, 0), scale=1.2, color=color.rgb(255, 255, 255), z=2.5)
    ls_panel = Entity(parent=camera.ui, model='quad',
                      color=color.rgba(20, 20, 20, 200),
                      scale=(0.8, 0.68), z=25)            # ★ 面板沉底（按钮 2.0 在其前）
    lv1 = Button(parent=camera.ui, text='第一关 · 潮湿回廊', position=(0, 0.16),
                 scale=(0.62, 0.075), z=2.0, color=color.rgb(35, 70, 45),
                 on_click=lambda: start_level(1))
    lv1.text_entity.scale = 1
    lv1.text_entity.color = color.rgb(200, 255, 220)
    lv2 = Button(parent=camera.ui, text='第二关 · 地下二层', position=(0, 0.02),
                 scale=(0.62, 0.075), z=2.0, color=color.rgb(90, 60, 25),
                 on_click=lambda: start_level(2))
    lv2.text_entity.scale = 1
    lv2.text_entity.color = color.rgb(255, 230, 180)
    # ★ 第三关按钮：核心实验室（硬编码走廊+房间）
    lv3 = Button(parent=camera.ui, text='第三关 · 核心实验室', position=(0, -0.11),
                 scale=(0.62, 0.075), z=2.0, color=color.rgb(110, 30, 30),
                 on_click=lambda: start_level(3))
    lv3.text_entity.scale = 1
    lv3.text_entity.color = color.rgb(255, 170, 170)
    ls_desc1 = Text(parent=camera.ui, text='迷宫 · 保险丝 ×3 · 聆听者',
                    position=(0, 0.075), origin=(0, 0), scale=1,
                    color=color.rgb(170, 170, 170), z=2.5)
    ls_desc2 = Text(parent=camera.ui, text='多层楼梯 · 柜子 · 管子 · 三扇门',
                    position=(0, -0.045), origin=(0, 0), scale=1,
                    color=color.rgb(170, 170, 170), z=2.5)
    ls_desc3 = Text(parent=camera.ui, text='推拉门 · 手术台 · 门禁卡 · 残缺报告',
                    position=(0, -0.175), origin=(0, 0), scale=1,
                    color=color.rgb(170, 170, 170), z=2.5)
    lv_back = Button(parent=camera.ui, text='返回主菜单', position=(0, -0.25),
                     scale=(0.3, 0.06), z=2.0, color=color.rgb(60, 60, 70),
                     on_click=lambda: open_menu())
    lv_back.text_entity.scale = 1
    lv_back.text_entity.color = color.rgb(255, 255, 255)
    _add_to_group('level_select', ls_mask, ls_panel, ls_title, lv1, lv2, lv3,
                  ls_desc1, ls_desc2, ls_desc3, lv_back)

    # ================= 残存记忆（档案库）——规格二：10 行解锁列表 =================
    ar_mask = Entity(parent=camera.ui, model='quad',
                     color=color.rgba(20, 20, 20, 200),
                     scale=(window.aspect_ratio, 1), z=30)  # ★ 底板沉底
    ar_title = Text(parent=camera.ui, text='残 存 记 忆 · 档 案 库',
                    origin=(0, 0), y=0.44, scale=1.1,
                    color=color.rgb(230, 200, 160), z=5)
    ar_stats = Text(parent=camera.ui, text='',
                    origin=(0, 0), y=0.37, scale=1,
                    color=color.rgb(170, 200, 170), z=5)
    archive_rows = []
    for i in range(len(LORE_ARCHIVE)):
        row = Button(parent=camera.ui, text='？？？',
                     scale=(0.6, 0.05), y=0.28 - i * 0.06, z=5,
                     color=color.rgb(25, 25, 28), highlight_color=color.red)
        row.on_click = Func(open_lore_read, i)   # ★ 规格三.1：Func 绑定（杜绝 lambda 闭包陷阱）
        row.text_entity.scale = 1
        row.text_entity.color = color.rgb(200, 195, 185)
        archive_rows.append(row)
        _add_to_group('archive', row)
    ar_back = Button(parent=camera.ui, text='返回主菜单',
                     scale=(0.3, 0.06), y=-0.36, z=5,
                     color=color.dark_gray, highlight_color=color.red)
    ar_back.on_click = open_menu
    _add_to_group('archive', ar_mask, ar_title, ar_stats, ar_back)
    # ---- 阅读子面板（★ 规格一.1：改为每次打开时销毁重建，见
    #      _build_lore_read_panel —— 彻底杜绝旧 UI 重叠/残留导致的黑屏无字）----
    lr_mask = lr_title = lr_text = lr_close = None
    # ★ 规格三：失忆开场独白（第一关进入时显示）
    global intro_text
    intro_text = Text(parent=camera.ui, text='', origin=(0, 0),
                      scale=1.15, color=color.rgb(210, 205, 195), z=6,
                      wordwrap=24)
    intro_text.enabled = False

    # ================= 设置（★ 规格二：遮罩/面板无碰撞体 Entity，
    # z=1.0/1.5 垫底；按钮 z=2.0 可点击；文字 z=2.5）=================
    set_mask = Entity(parent=camera.ui, model='quad',
                      color=color.rgba(20, 20, 20, 200),  # ★ 规格深灰半透明
                      scale=(window.aspect_ratio, 1), z=30)  # ★ 底板沉底
    set_panel = Entity(parent=camera.ui, model='quad',
                       color=color.rgba(20, 20, 20, 200),
                       scale=(0.6, 0.4), z=25)            # ★ 面板沉底
    set_title = Text(parent=camera.ui, text='设 置', position=(0, 0.14),
                     origin=(0, 0), scale=1.2, color=color.rgb(255, 255, 255), z=2.5)
    sens_label = Text(parent=camera.ui, text='鼠标灵敏度', position=(-0.14, 0.0),
                      origin=(0, 0), scale=1,
                      color=color.rgb(240, 240, 240), z=2.5)
    sens_minus = Button(parent=camera.ui, text='-', position=(0.08, 0.0),
                        scale=(0.07, 0.06), z=2.0, color=color.rgb(90, 25, 25),
                        on_click=lambda: change_sensitivity(-5))
    sens_value_text = Text(parent=camera.ui, text='', position=(0.16, 0.0),
                           origin=(0, 0), scale=1,
                           color=color.rgb(140, 255, 180), z=2.5)
    sens_plus = Button(parent=camera.ui, text='+', position=(0.23, 0.0),
                       scale=(0.07, 0.06), z=2.0, color=color.rgb(90, 25, 25),
                       on_click=lambda: change_sensitivity(+5))
    # ★ F11 全屏切换提示（规格三.2）
    fullscreen_hint = Text(parent=camera.ui, text='按 T 切换全屏 / 半屏',
                           position=(0, -0.06), origin=(0, 0), scale=1,
                           color=color.rgb(170, 200, 255), z=2.5)
    # ★ 规格一：开发者模式按钮（dark_red，点击一键解锁全剧情）
    dev_btn = Button(parent=camera.ui, text='开发者模式(解锁全剧情)',
                     position=(0, -0.14), scale=(0.44, 0.055), z=5,
                     color=color.rgb(90, 20, 20),   # ★ dark_red（ursina 5.2 无该常量，等效深红）
                     highlight_color=color.red)
    dev_btn.on_click = unlock_all_lore
    dev_btn.text_entity.scale = 1
    dev_btn.text_entity.color = color.rgb(255, 200, 200)
    set_back = Button(parent=camera.ui, text='返回主菜单', position=(0, -0.22),
                      scale=(0.3, 0.06), z=5, color=color.rgb(60, 60, 70),
                      on_click=lambda: open_menu())
    set_back.text_entity.scale = 1
    set_back.text_entity.color = color.rgb(255, 255, 255)
    set_panel.scale = (0.6, 0.52)           # ★ 面板加高容纳新按钮
    _add_to_group('settings', set_mask, set_panel, set_title, sens_label, sens_minus,
                  sens_value_text, sens_plus, fullscreen_hint, dev_btn, set_back)

    # ================= 局内 HUD（★ 文字 scale=1，全部 parent=camera.ui）=================
    hint_text = Text(parent=camera.ui,
                     text='WASD移动 | Shift跑 | 左键潜行+Q屏息 | 右键回声 | F投掷 | E交互 | Esc暂停',
                     position=window.bottom_left + Vec2(0.015, 0.015),
                     origin=(-0.5, -0.5), scale=1, color=color.rgb(160, 160, 160),
                     z=2.0)
    echo_text = Text(parent=camera.ui, text='回声：就绪',
                     position=window.bottom_left + Vec2(0.015, 0.06),
                     origin=(-0.5, -0.5), scale=1, color=color.rgb(90, 160, 220),
                     z=2.0)
    status_text = Text(parent=camera.ui, text='', position=(0, 0.46), origin=(0, 0),
                       scale=1, color=color.rgb(255, 230, 150), z=2.0)
    update_status_text()
    stamina_bg = Entity(parent=camera.ui, model='quad', color=color.rgb(25, 25, 25),
                        scale=(0.64, 0.04), position=(0, -0.42), z=30)  # ★ 沉底
    stamina_fill = Entity(parent=camera.ui, model='quad', color=color.rgb(60, 220, 90),
                          origin=(-0.5, 0), position=(-0.31, -0.42),
                          scale=(0.62, 0.028), z=1.5)
    stamina_label = Text(parent=camera.ui, text='体力', position=(-0.345, -0.42),
                         origin=(0.5, 0), scale=1, color=color.rgb(120, 120, 120),
                         z=2.0)
    # ★ 规格一.1：模型缺失警告（屏幕正中央红字，默认隐藏）
    global model_warn_text
    model_warn_text = Text(parent=camera.ui,
                           text='[警告] 未找到怪物模型文件，请检查路径',
                           origin=(0, 0), scale=1.1,
                           color=color.rgb(255, 40, 40), z=6.0)
    model_warn_text.enabled = (MONSTER_OBJ_PATH is None)
    # ★ 规格三.1：恐怖值进度条（红色，体力条下方）
    fear_bg = Entity(parent=camera.ui, model='quad', color=color.rgb(40, 10, 10),
                     scale=(0.64, 0.03), position=(0, -0.47), z=30)  # ★ 沉底
    fear_fill = Entity(parent=camera.ui, model='quad', color=color.rgb(200, 30, 30),
                       origin=(-0.5, 0), position=(-0.31, -0.47),
                       scale=(0.0001, 0.02), z=1.5)
    fear_label = Text(parent=camera.ui, text='恐惧', position=(-0.345, -0.47),
                      origin=(0.5, 0), scale=1, color=color.rgb(150, 60, 60),
                      z=2.0)
    # ★ 屏息氧气条（蓝色）：仅在按住 Q 屏息时显示（宽度绑定 oxygen，规格要求）
    o2_bg = Entity(parent=camera.ui, model='quad', color=color.rgb(20, 25, 40),
                   scale=(0.64, 0.032), position=(0, -0.455), z=30)  # ★ 沉底
    o2_fill = Entity(parent=camera.ui, model='quad', color=color.rgb(90, 170, 255),
                     origin=(-0.5, 0), position=(-0.31, -0.455),
                     scale=(0.62, 0.022), z=1.5)
    o2_label = Text(parent=camera.ui, text='氧气', position=(-0.345, -0.455),
                    origin=(0.5, 0), scale=1, color=color.rgb(120, 140, 170),
                    z=2.0)
    o2_bg.enabled = False
    o2_fill.enabled = False
    o2_label.enabled = False
    prompt_text = Text(parent=camera.ui, text='— 按 E 交互 —', position=(0, -0.16),
                       origin=(0, 0), scale=1, color=color.rgb(255, 220, 120),
                       z=2.0)
    prompt_text.enabled = False
    _add_to_group('hud', hint_text, echo_text, status_text, stamina_bg, stamina_fill,
                  stamina_label, prompt_text)

    # ================= 暂停 / 死亡 / 胜利 =================
    pause_title = Text(parent=camera.ui, text='已 暂 停', position=(0, 0.25),
                       origin=(0, 0), scale=1.2, color=color.rgb(230, 230, 230), z=2.5)
    pause_hint = Text(parent=camera.ui, text='Esc 继续 | R 重新开始 | Q 返回主菜单',
                      position=(0, 0.1), origin=(0, 0), scale=1,
                      color=color.rgb(180, 180, 180), z=2.5)
    _add_to_group('pause', pause_title, pause_hint)
    death_text = Text(parent=camera.ui, text='GAME OVER，按 R 重开\n按 Q 返回主菜单',
                      origin=(0, 0), position=(0, -0.12), scale=1.2,
                      color=color.red, z=-0.85)
    death_text.enabled = False
    win_text = Text(parent=camera.ui, text='', origin=(0, 0), position=(0, 0),
                    scale=1.2, color=color.rgb(90, 255, 140), z=-0.85)
    win_text.enabled = False


# =====================================================================================
#  十二、局外界面逻辑与游戏流程
# =====================================================================================
def apply_mouse_state():
    """★ 鼠标状态机（极其重要，修复"鼠标无法点击"）：
    非 PLAYING 状态（主菜单/子面板/暂停/死亡/胜利/阅读日记）一律强制
    mouse.locked=False 且 mouse.visible=True——光标可见、可自由移动点击按钮；
    仅 PLAYING（且未在阅读日记）时锁定鼠标。所有状态切换必须调用本函数。"""
    try:
        if game_state == GameState.PLAYING and not diary_open:
            mouse.locked = True
            mouse.visible = False
        else:
            mouse.locked = False
            mouse.visible = True
    except Exception:
        pass


def set_menu_buttons_disabled(disabled):
    for btn in menu_buttons:
        btn.disabled = disabled


def open_menu():
    """回到主菜单：清理局内世界并复位所有子面板标志"""
    global game_state, settings_open, level_select_open, archive_open, lore_read_open
    level_manager.teardown()
    close_diary()                           # 安全复位：合上可能开着的日记弹窗
    set_peek_mask(False)                    # 安全复位：撤掉柜内窥视遮罩
    close_diary()                           # 安全复位：合上可能开着的日记弹窗
    # ★ 停止全部循环环境音（含新增的雷雨声）——回到菜单恢复安静
    try:
        for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio,
                  thunderstorm_audio):
            if a is not None:
                a.stop()
    except Exception:
        pass
    if thunder_active:
        _thunder_end()                     # ★ 回菜单时收尾雷暴（防环境光泄漏）
    game_state = GameState.MENU
    settings_open = False
    level_select_open = False
    archive_open = False
    lore_read_open = False
    apply_mouse_state()                     # ★ 鼠标状态机：解锁并显示光标
    set_menu_buttons_disabled(False)
    show_group('menu')
    death_text.enabled = False
    win_text.enabled = False
    reset_vignette()


def open_level_select():
    """关卡选择（★ 独立状态 LEVEL_SELECT，规格要求）"""
    global game_state, settings_open, archive_open, lore_read_open
    level_manager.teardown()
    close_diary()                           # 安全复位
    set_peek_mask(False)
    settings_open, archive_open, lore_read_open = False, False, False
    game_state = GameState.LEVEL_SELECT
    apply_mouse_state()                     # ★ 鼠标状态机：解锁并显示光标
    show_group('level_select')


def open_archive():
    """残存记忆（档案库）：按碎片解锁进度刷新 10 行条目（主菜单子面板）"""
    global archive_open, lore_read_open, settings_open, level_select_open
    level_manager.teardown()
    close_diary()
    set_peek_mask(False)
    archive_open, lore_read_open = True, False
    settings_open, level_select_open = False, False
    game_state = GameState.MENU
    apply_mouse_state()
    set_menu_buttons_disabled(True)
    refresh_archive()
    show_group('archive')


def unlock_all_lore():
    """★ 开发者模式（规格二）：一键解锁全部 10 段档案文本。
    只改写文本解锁标记并持久化到 save_data.json——绝不触碰怪物生态、
    恐怖值与游戏平衡；档案库若正开着会立即刷新为可点击阅读状态。"""
    global dev_all_unlocked
    dev_all_unlocked = True
    # 内存中的已收集碎片列表强行填满（50 个不同 ID，供碎片统计显示）
    collected_fragment_ids[:] = list(range(len(FRAGMENT_POOL)))
    save_fragment_data()                    # ★ 同步写入 save_data.json 永久生效
    refresh_archive()                       # ★ 强制刷新档案库 UI（？？？→可阅读）
    show_toast('开发者模式已激活，全剧情已解锁！')
    print('开发者模式已激活，全剧情已解锁！')


def refresh_archive():
    """★ 规格三.2：解锁规则 = 已收集不重复碎片数 // 10（每 10 个解锁 1 段）"""
    frag_n = len(collected_fragment_ids)
    unlock_count = (10 if dev_all_unlocked
                    else min(10, frag_n // 10))
    try:
        ar_stats.text = (f'已收集碎片: {frag_n} / 50    '
                         f'已解锁记忆: {unlock_count} / 10')
    except Exception:
        pass
    for i, row in enumerate(archive_rows):
        if i < unlock_count:
            row.text = LORE_ARCHIVE[i]['title']
            row.color = color.rgb(60, 50, 40)
            row.highlight_color = color.red
            if row.text_entity is not None:
                row.text_entity.color = color.rgb(235, 220, 190)
        else:
            row.text = '？？？'
            row.color = color.rgb(25, 25, 28)
            row.highlight_color = color.rgb(25, 25, 28)
            if row.text_entity is not None:
                row.text_entity.color = color.rgb(90, 90, 92)


def wrap_text(text, width=35):
    """★ 规格一.3：强制中文换行——严禁直接渲染超长字符串。
    按每行 35 字符硬切片插入换行符（中文按字符计，绝不飞出屏幕）。"""
    return '\n'.join([text[i:i + width] for i in range(0, len(text), width)])


_lore_panel_entities = []     # 当前阅读面板实体（每次打开重建，防重叠/残留）


def _build_lore_read_panel(title, body):
    """★ 规格一.1：强制清理旧 UI 后重建阅读面板（destroy 旧实体再创建新的）。
    Z 序（像素实测终版）：camera.ui 中 z 越小越靠前（负数最前）——
    现行截图实测 z=+6 的文字被 z=5 的列表行遮死（TEXT-MISSING），
    而规格的 bg z=-10 / 文字 z=-11 完美可见（TEXT-VISIBLE）。
    故按规格锁定：背景板 -10、文字/按钮 -11，绝对置顶。"""
    global lr_mask, lr_title, lr_text, lr_close
    # ---- 1. 销毁上一次的面板实体（并从 UI 组摘除，防止重叠/渲染残留）----
    for e in _lore_panel_entities[:]:
        try:
            destroy(e)
        except Exception:
            pass
        try:
            ui_groups.get('lore_read', []).remove(e)
        except (ValueError, KeyError):
            pass
    _lore_panel_entities.clear()
    # ---- 2. 重建：背景板（深色半透明 rgba(10,10,10,240)，1.6×0.9 居中）----
    lr_mask = Entity(parent=camera.ui, model='quad',
                     color=color.rgba(0, 0, 0, 240),   # ★ 规格二.3：纯黑半透明
                     scale=(1.6, 0.9), position=(0, 0), z=-10)   # ★ 规格：bg z=-10
    lr_title = Text(parent=camera.ui, text=title, origin=(0, 0), y=0.36,
                    scale=0.9, color=color.rgb(255, 220, 150), z=-11)
    # ---- 3. 正文：wrap_text 强制换行 + scale=0.8 + 亮白（规格一.3/一.4）----
    lr_text = Text(parent=camera.ui, text=wrap_text(body, width=35),
                   origin=(0, 0), y=-0.03, scale=0.8,
                   color=color.white, z=-11)   # ★ 规格二.3：文字 z=-11，绝对在背景板前
    lr_close = Button(parent=camera.ui, text='合上（Esc）',
                      scale=(0.3, 0.06), y=-0.38, z=-11,
                      color=color.dark_gray, highlight_color=color.red)
    lr_close.on_click = close_lore_read
    _lore_panel_entities.extend([lr_mask, lr_title, lr_text, lr_close])
    for e in _lore_panel_entities:
        _add_to_group('lore_read', e)


def open_lore_read(i):
    """展开一段已解锁的长文本（每次销毁重建面板 + 强制换行）"""
    global lore_read_open
    unlock_count = (10 if dev_all_unlocked
                    else min(10, len(collected_fragment_ids) // 10))
    if i >= unlock_count:
        show_toast('这段记忆还没想起来……（收集局内碎片解锁）')
        return
    lore_read_open = True
    _build_lore_read_panel(LORE_ARCHIVE[i]['title'], LORE_ARCHIVE[i]['text'])
    show_group('archive', 'lore_read')


def close_lore_read():
    global lore_read_open
    lore_read_open = False
    show_group('archive')


def open_settings():
    global settings_open, level_select_open, archive_open, lore_read_open
    settings_open, level_select_open, archive_open, lore_read_open = True, False, False, False
    apply_mouse_state()                     # ★ 鼠标状态机：解锁并显示光标
    refresh_settings_ui()
    show_group('settings')


def refresh_settings_ui():
    sens_value_text.text = str(int(SAVE['settings']['sensitivity']))


def change_sensitivity(delta):
    if not settings_open:
        return
    SAVE['settings']['sensitivity'] = float(
        clamp(SAVE['settings']['sensitivity'] + delta, 15, 80))
    write_save()
    refresh_settings_ui()


def start_level(level_id):
    """开始某一关：清理旧场景 → 随机词条 → 生成关卡 → 进入 PLAYING"""
    global game_state, current_level, player_lives, collected_fuses, collected_diaries
    global active_modifier, scare_ambience_timer
    current_level = level_id
    active_modifier = random.choice(MODIFIERS)      # ★ 随机词条（每局不同）
    scare_ambience_timer = random.uniform(*SCARE_AMBIENCE_INTERVAL)  # 惊吓计时重置
    level_manager.load_level(level_id)
    player_lives = get_start_lives()
    collected_fuses = 0
    collected_diaries = 0
    game_state = GameState.PLAYING
    apply_mouse_state()                     # ★ 鼠标状态机：锁定鼠标进入游玩
    show_group('hud')
    minimap_panel.enabled = False
    death_text.enabled = False
    win_text.enabled = False
    taunt_text.enabled = False
    set_peek_mask(False)
    blur_overlay.enabled = bool(active_modifier.get('vision_blur'))
    if blur_overlay.enabled:
        blur_overlay.color = color.rgba(60, 60, 66, 95)
    reset_vignette()
    prompt_text.enabled = False
    update_status_text()
    echo_text.text = '回声：就绪'
    show_toast(f'本局词条【{active_modifier["name"]}】：{active_modifier["desc"]}')
    try:
        # ★ 随机 BGM（规格：每次进入 PLAYING / 进入关卡时随机选一首循环播放；
        #   用户 mp3 缺失时自动回退到内置合成 BGM）
        play_random_bgm()
        if wind_audio is not None:
            wind_audio.play()
        if breath_audio is not None:
            breath_audio.play()
        if heartbeat_audio is not None:
            heartbeat_audio.volume = 0.0
            heartbeat_audio.play()
        # ★ 雷雨环境音（规格：进入关卡 / PLAYING 状态时循环播放；
        #   用户 mp3 缺失时自动退化为合成雷雨声，再缺失则静音）
        if thunderstorm_audio is not None:
            thunderstorm_audio.volume = 0.30 * (
                0.6 if (active_modifier and active_modifier.get('quiet')) else 1.0)
            thunderstorm_audio.play()
    except Exception:
        pass


def pause_game():
    global game_state
    if game_state != GameState.PLAYING or diary_open:
        return
    if player is not None:
        player.is_holding_breath = False       # 暂停时释放屏息（防止冻结在屏息态）
    game_state = GameState.PAUSED
    apply_mouse_state()                     # ★ 鼠标状态机：解锁并显示光标
    show_group('hud', 'pause')


def resume_game():
    global game_state
    if game_state != GameState.PAUSED:
        return
    game_state = GameState.PLAYING
    apply_mouse_state()                     # ★ 鼠标状态机：重新锁定鼠标
    show_group('hud')


def start_jumpscare(performer):
    """突脸：performer.play_jumpscare() 把自己摆到镜头前 + 尖叫 + 剧烈抖动
    + ★ 屏幕黑白化 + ★ 随机英文嘲讽（规格四），0.7 秒后结算扣命。"""
    global scare_active, scare_timer
    if scare_active or game_state != GameState.PLAYING:
        return
    scare_active = True
    scare_timer = SCARE_DURATION
    pause_all_game_audio()                  # ★ 规格二.3：突脸瞬间强制静音全场
    performer.play_jumpscare()
    play_sfx('jumpscare', volume=1.0)
    play_sfx('monster_scream', volume=1.0)  # ★ 规格二.1：突脸只播怪物尖叫
    # ★ 屏幕黑白化：灰白罩闪现后淡出（GAME OVER 时由 lose_life 常驻）
    _gray_step(200)
    invoke(_gray_step, 90, delay=0.25)
    invoke(_gray_step, 0, delay=0.6)
    # ★ 规格二.2：男声嘲讽延后——重生传送 / GAME OVER 时才播放（见 lose_life）
    _scare_flash_step(190)
    invoke(_scare_flash_step, 110, delay=0.15)
    invoke(_scare_flash_step, 50, delay=0.3)
    invoke(_scare_flash_step, 0, delay=0.45)
    print('【突脸】呃啊啊啊啊啊——！！！')


_taunt_audio_cache = {}


def _play_taunt_voice(idx):
    """★ 死亡嘲讽男声（规格修复）：显式加载 assets/sounds/voice_taunt_N.mp3 并
    强制 play()——Audio 独立于游戏状态机，DEAD 状态（黑白屏/抖动/暂停语义）下
    照常出声，绝不被打断。加载失败红色警告 + 合成兜底，绝不静默。"""
    name = f'voice_taunt_{idx + 1}'
    aud = _taunt_audio_cache.get(name, 'MISS')
    if aud == 'MISS':
        path = os.path.join(SOUND_DIR, name + '.mp3')   # 规格路径
        aud = None
        if os.path.isfile(path):                        # ★ 路径强校验
            # ★ 规格五.1：音量拉到 1.5（Panda 支持增益 >1）；引擎拒绝则回退 1.0
            try:
                aud = Audio(path, volume=1.5, autoplay=True)
                print(f'✅ 音频加载成功: {name}.mp3（音量 1.5）')
            except Exception:
                try:
                    aud = Audio(path, volume=1.0, autoplay=True)
                    print(f'✅ 音频加载成功: {name}.mp3（音量 1.0）')
                except Exception:
                    aud = None
        if aud is None:
            print('\033[91m[严重警告] 死亡嘲讽音效加载失败，请检查路径和文件格式\033[0m')
            try:                                # 合成兜底（绝不静音）
                aud = load_audio(f'taunt{idx + 1}')
            except Exception:
                aud = None
        _taunt_audio_cache[name] = aud
    if aud is not None:
        try:
            try:
                aud.volume = 1.5                # ★ 规格五.1：合成兜底路径也拉满
            except Exception:
                pass
            aud.play()                          # ★ 显式强制播放
        except Exception as ex:
            print(f'\033[91m[严重警告] 死亡嘲讽音效播放失败: {ex}\033[0m')
            try:
                aud.play()
            except Exception:
                pass


# ---- ★ 规格二：Audio Ducking（音频弱化）基准音量表 ----
# 嘲讽人声响起的瞬间，BGM/环境音平滑压到基准的 20%，语音结束后恢复。
_AUDIO_BASE_VOL = {'bgm': 0.32, 'wind': 0.30, 'breath': 0.35, 'thunder': 0.30}


def _duck_targets():
    """可弱化的背景音频对象（心跳由恐怖值驱动，不参与弱化）"""
    return [('bgm', bgm_audio), ('wind', wind_audio),
            ('breath', breath_audio), ('thunder', thunderstorm_audio)]


_duck_target_vols = {}        # 各背景音的弱化目标音量（每帧 lerp 逼近）


def duck_audio(volume_level):
    """★ 规格三：Audio Ducking——volume_level 为音量系数
    （0.1=压到基准 10%，1.0=恢复满值）。实现用与心跳/近墙相同的逐帧 lerp
    平滑收敛（约 0.5 秒压低 / 1 秒恢复）。"""
    for name, aud in _duck_targets():
        if aud is None:
            continue
        base = _AUDIO_BASE_VOL.get(name, 0.3)
        _duck_target_vols[name] = base * volume_level


def _thunder_set_ambient(bright):
    """★ 规格五.2：雷暴提亮/恢复环境光（冷色调——能看见远处墙壁）"""
    if ambient_light is None:
        return
    try:
        ambient_light.color = (color.rgb(110, 120, 140) if bright
                               else color.rgb(5, 5, 5))
    except Exception:
        try:
            ambient_light.setColor(color.rgb(110, 120, 140) if bright
                                   else color.rgb(5, 5, 5))
        except Exception:
            pass


def _thunder_start():
    """★ 规格五：雷暴开始——炸雷音效 + 环境光提亮 + 全部怪物立刻 CHASE 玩家"""
    global thunder_active, thunder_left
    thunder_active = True
    thunder_left = THUNDER_DURATION
    play_sfx('thunder_burst', volume=1.0)
    _thunder_set_ambient(True)
    print('【雷暴】轰隆——！！闪电撕开黑暗，它们全都听见你了！！')
    if player is not None:
        for m in list(MONSTERS):
            if not m.is_dead:
                m.hear_noise(player.position, 1e9)   # 全图：立刻 CHASE 玩家当前位置


def _thunder_end():
    """★ 规格五.3：雷暴结束——恢复极暗，怪物退回 SEARCH"""
    global thunder_active, thunder_timer, thunder_left
    thunder_active = False
    thunder_left = 0.0
    thunder_timer = THUNDER_INTERVAL
    _thunder_set_ambient(False)
    for m in list(MONSTERS):
        if not m.is_dead and m.state == 'CHASE':
            m.state = 'SEARCH'
            m.search_timer = 3.0
    print('【雷暴】雷声远去……黑暗重新合拢。它们在原地搜索着什么。')


def _thunder_update(dt):
    """★ 规格五：雷暴主循环（PLAYING 状态每帧调用，全部 try 防空指针）"""
    global thunder_timer, thunder_left, thunder_los_timer
    if not thunder_active:
        thunder_timer -= dt
        if thunder_timer <= 0:
            _thunder_start()
        return
    thunder_left -= dt
    if thunder_left <= 0:
        _thunder_end()
        return
    # ---- 雷暴期：怪物每 0.5 秒做一次 LOS 射线——无墙阻挡即"看见"玩家 ----
    thunder_los_timer -= dt
    if thunder_los_timer <= 0:
        thunder_los_timer = 0.5
        if player is None:
            return
        for m in list(MONSTERS):
            if m.is_dead or m.state != 'CHASE':
                continue
            try:
                o = Vec3(m.x, m.y + 1.6, m.z)
                tp = Vec3(player.x, player.y + 1.2, player.z)
                dvec = tp - o
                d = dvec.length()
                if d < 0.5:
                    m.noise_target = Vec3(player.position.x, 0, player.position.z)
                    continue
                hit = raycast(o, Vec3(dvec.x / d, dvec.y / d, dvec.z / d),
                              distance=d, ignore=(m, player))
                blocked = (hit is not None and hit.entity is not None
                           and getattr(hit.entity, 'is_terrain', False))
                if not blocked:      # 看见玩家 → 目标刷新为玩家实时位置
                    m.noise_target = Vec3(player.x, 0, player.z)
                    m.path = [Vec3(m.noise_target.x, 0, m.noise_target.z)]
            except Exception:
                pass


def pause_all_game_audio():
    """★ 规格二：死亡突脸瞬间强制静音——遍历 BGM/环境音/怪物喘息/心跳
    执行 .pause()（失败则 volume=0），让嘲讽男声独占听觉。"""
    for aud in (bgm_audio, wind_audio, breath_audio,
                thunderstorm_audio, heartbeat_audio):
        if aud is None:
            continue
        try:
            aud.pause()
        except Exception:
            try:
                aud.volume = 0
            except Exception:
                pass
    for m in list(MONSTERS):                    # 怪物循环喘息（脚步为单次不暂停）
        if getattr(m, 'is_dead', False):
            continue
        aud = getattr(m, 'breath_aud', None)
        if aud is not None:
            try:
                aud.pause()
            except Exception:
                pass
    for a in list(AMBIENT_SOUNDS3D):            # 房间 3D 环境音
        if a.audio is not None:
            try:
                a.audio.pause()
            except Exception:
                pass
    print('【混音】全部游戏音频已暂停（嘲讽独占听觉）')


def resume_all_game_audio():
    """★ 规格二.4：嘲讽播完后恢复全部游戏音频（GAME OVER 保持寂静）。"""
    if game_state == GameState.DEAD:
        return
    duck_audio(1.0)                             # 重置弱化目标为基准音量
    for aud in (bgm_audio, wind_audio, breath_audio,
                thunderstorm_audio, heartbeat_audio):
        if aud is None:
            continue
        try:
            aud.play()
        except Exception:
            pass
    for m in list(MONSTERS):
        if getattr(m, 'is_dead', False):
            continue
        aud = getattr(m, 'breath_aud', None)
        if aud is not None:
            try:
                aud.play()
            except Exception:
                pass
    for a in list(AMBIENT_SOUNDS3D):
        if a.audio is not None:
            try:
                a.audio.play()
            except Exception:
                pass
    print('【混音】游戏音频已恢复')


def _show_taunt():
    """★ 随机英文嘲讽（男声 + 屏幕字幕），2.5 秒后隐藏（规格四）。
    ★ 突脸扣命与 GAME OVER 两条死亡路径都会调用本函数——男声强制触发。"""
    _taunt_token[0] += 1
    idx = random.randrange(len(TAUNTS))
    taunt_text.text = f'"{TAUNTS[idx]}"'
    taunt_text.enabled = True
    _play_taunt_voice(idx)                      # ★ 显式加载 + 强制 play()
    invoke(resume_all_game_audio, delay=4.0)    # ★ 规格二.4：嘲讽播完（约4秒）恢复全场
    invoke(_hide_taunt, _taunt_token[0], delay=2.5)


def _hide_taunt(token=None):
    """隐藏嘲讽字幕（令牌守卫：只隐藏最新一条）"""
    if token is None or token == _taunt_token[0]:
        taunt_text.enabled = False


def lose_life():
    """★ 3 条命系统：扣 1 命（死亡复活保留日记与保险丝）。
    有命 → 晕影脉冲 + 回出生点重生 + 怪物/丝线复位；命尽 → 黑白化 + 嘲讽 + GAME OVER。"""
    global player_lives, game_state
    player_lives -= 1
    update_status_text()
    if player_lives > 0:
        set_vignette_instant(1.0)
        safe_pos = find_safe_spawn()
        _show_taunt()                       # ★ 规格二.2：还有命 → 重生传送时播放嘲讽
        if safe_pos is not None and player is not None:
            player.spawn_position = Vec3(safe_pos.x, safe_pos.y, safe_pos.z)
        if player is not None:
            player.respawn()                    # ★ 保留保险丝与日记计数
        for m in list(MONSTERS):
            if not m.is_dead:
                m.reset()
        for s in list(SPIDERS):                 # 已触发的丝线不再重复杀人
            if not s.is_dead and s.triggered:
                s.reset()
        print(f'【生命】你被抓住了！剩余生命 ×{player_lives}'
              f'（保险丝 {collected_fuses} · 日记 {collected_diaries} 已保留）')
    else:
        # ---- 生命耗尽：黑白化 + 随机英文嘲讽（语音+字幕）+ GAME OVER ----
        game_state = GameState.DEAD
        apply_mouse_state()                 # ★ 鼠标状态机：解锁并显示光标
        prompt_text.enabled = False
        set_peek_mask(False)
        death_text.enabled = True
        set_vignette_instant(1.0)
        _show_taunt()                       # ★ 规格二.2：GAME OVER 时播放嘲讽
        _gray_step(230)                          # 白闪
        invoke(_gray_step, 120, delay=0.25)      # 落回灰白（黑白化常驻）
        _show_taunt()                            # ★ 随机英文嘲讽（语音+字幕）
        # ---- ★ 叙事结算：本局碎片已实时写入档案库进度（无代币）----
        try:
            for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio,
                      thunderstorm_audio):
                if a is not None:
                    a.stop()
        except Exception:
            pass


def win_game():
    """触碰真实出口（且保险丝集齐）→ WIN + 代币结算"""
    global game_state
    if game_state != GameState.PLAYING:
        return
    game_state = GameState.WIN
    apply_mouse_state()                     # ★ 鼠标状态机：解锁并显示光标
    prompt_text.enabled = False
    set_peek_mask(False)
    write_save()
    win_text.text = (f'你逃出来了！\nYOU ESCAPED'
                     f'\n本局收集：保险丝 {collected_fuses} · 日记 {collected_diaries}'
                     f'\n档案库已解锁 '
                     f'{min(10, len(collected_fragment_ids) // 10)} / 10 段残存记忆'
                     f'\n按 R 再来一局 | Q 返回主菜单')
    win_text.enabled = True
    reset_vignette()
    play_sfx('skill', volume=0.8)
    try:
        for a in (bgm_audio, wind_audio, breath_audio, heartbeat_audio,
                  thunderstorm_audio):
            if a is not None:
                a.stop()
    except Exception:
        pass


def trigger_ambush(gate):
    """★ 选错出口：把最近的聆听者传送到玩家身后 8 米并发起追击（伏击）"""
    if not MONSTERS:
        return
    nearest, nd = None, 1e9
    for m in list(MONSTERS):
        if m.is_dead:
            continue
        d = dist_xz(m.position, player.position)
        if d < nd:
            nearest, nd = m, d
    if nearest is None:
        return
    back = -camera.forward                     # 玩家背后
    nearest.position = Vec3(player.x + back.x * 8.0, 0, player.z + back.z * 8.0)
    tile = level_manager.nearest_floor_tile(nearest.position)
    w = level_manager.tile_to_world(tile)
    nearest.position = Vec3(w.x, 0, w.z)        # 吸附到地板格防卡墙
    nearest.state = 'CHASE'
    nearest.noise_target = Vec3(player.x, 1.5, player.z)
    cells = level_manager.bfs_path(level_manager.world_to_tile(nearest.position),
                                   level_manager.world_to_tile(player.position))
    nearest.path = [level_manager.tile_to_world(t) for t in cells] \
        if cells else [nearest.noise_target]
    gate.ambushed = True                        # 假门转为暗红警示
    play_sfx('roar', volume=1.0)
    print('【伏击】铰链断裂的巨响——这扇门是假的！身后传来了嘶吼！！')


# =====================================================================================
#  十三、全局主循环与输入
# =====================================================================================
def update():
    """全局主循环：状态闸门 + 突脸抖动 + 墙体平滑线框 + 卡墙保护 + 保险丝指引
    + 出口/伏击判定（含高度）+ 危险晕影/心跳 + 随机环境音 + 小地图箭头 + 清道夫"""
    global scare_timer, buzz_timer, ambient_event_timer, danger_k, _scrape_timer
    global scare_ambience_timer

    # ★★ 规格二.1（最高优先级）：鼠标状态看门狗——
    # 非 PLAYING 状态（主菜单/关卡选择/暂停/死亡/胜利/阅读日记）强制
    # mouse.locked=False + mouse.visible=True。无论状态从哪里漂移，
    # 下一帧都会被纠正，从根上杜绝"回到菜单后鼠标点不了"。
    if (game_state != GameState.PLAYING or diary_open) \
            and (mouse.locked or not mouse.visible):
        apply_mouse_state()

    # ---- ★ Audio Ducking 平滑逼近（规格二：任何状态都收敛，含菜单嘲讽）----
    if _duck_target_vols:
        for _dn, _da in _duck_targets():
            if _da is None:
                continue
            _tv = _duck_target_vols.get(_dn)
            if _tv is not None:
                try:
                    _da.volume = lerp(_da.volume, _tv, min(time.dt * 6.0, 1.0))
                except Exception:
                    pass

    # ★ 防闪退铁律：非 PLAYING 状态一律跳过
    if game_state != GameState.PLAYING:
        return
    if player is None:
        return
    # ★ 阅读文本时游戏继续运行（规格一.3：怪物移动、玩家可移动），
    #   仅阻止新的交互——由 try_interact 内部判断。

    # ---- 0. 突脸：相机高频剧烈抖动，结束后结算扣命 ----
    if scare_active:
        scare_timer -= time.dt
        # ★ 规格四.2：镜头瞬间剧烈高频抖动（math.sin 高频）
        player.camera_pivot.x = math.sin(pytime.time() * 60) * 0.42
        player.camera_pivot.y = player._base_h + math.sin(pytime.time() * 55) * 0.3
        if scare_timer <= 0:
            scare_active_global_off()
            lose_life()
        return

    # ---- 1. 清道夫：销毁标记 is_dead 的回声球/投掷物/波纹 ----
    for lst in (ECHO_SPHERES, STONES, RIPPLES):
        for obj in list(lst):                   # ★ 浅拷贝遍历
            if getattr(obj, 'is_dead', False):
                lst.remove(obj)
                destroy(obj)

    # ---- 1.4 ★ 金属刮擦（规格一.5）：靠近培养罐/抽屉时随机播放 ----
    _scrape_timer -= time.dt
    if _scrape_timer <= 0:
        _scrape_timer = 5.0
        if player is not None:
            _near = [t for t in list(TANKS) + list(DRAWERS)
                     if not t.is_dead
                     and dist_xz(player.position, t.position) < 3.5]
            if _near and random.random() < 0.4:
                play_sfx('metal_scrape', volume=0.5,
                         pitch=random.uniform(0.85, 1.15))

    # ---- 1.5 ★ 规格二：线框淡出——animate_color 为主（8 秒平滑），
    #      引擎补间不可用时由本循环逐帧兜底；到点销毁由 _echo_restore 负责 ----
    for g in list(ECHO_GHOSTS):
        try:
            g.life -= time.dt
            if not getattr(g, '_auto_anim', False):
                a = int(255 * clamp(g.life / REVEAL_DURATION, 0.0, 1.0))
                _c = g.color
                g.color = color.rgba(int(_c[0] * 255), int(_c[1] * 255),
                                     int(_c[2] * 255), a)
            if g.life <= 0 and g in ECHO_GHOSTS:
                ECHO_GHOSTS.remove(g)           # 残留兜底清理
        except Exception:
            if g in ECHO_GHOSTS:
                ECHO_GHOSTS.remove(g)

    # ---- 1.55 ★ 规格五：五分钟雷暴（计时/提亮/怪物暴走 + LOS 射线）----
    try:
        _thunder_update(time.dt)
    except Exception:
        pass

    # ---- 1.6 ★ 规格二.3：单局碎片满 8 → 地图上未拾取的碎片实体全部消散 ----
    if current_round_fragments >= 8 and (DIARIES or REPORTS):
        for _d in list(DIARIES):
            if not _d.is_dead:
                safe_destroy(_d)
        for _r in list(REPORTS):
            if not _r.is_dead:
                safe_destroy(_r)
        DIARIES.clear()
        REPORTS.clear()

    # ---- 2. 墙体近距感知（平滑渐变 + 滞回，绝不闪烁）----
    for wall in list(WALLS):
        if wall.is_dead or wall.mode == Wall.MODE_ECHO:
            continue
        dx = wall.x - player.x
        dz = wall.z - player.z
        target = 0.0
        if abs(dx) <= WALL_SENSE_EXIT + 2 and abs(dz) <= WALL_SENSE_EXIT + 2:
            d = math.hypot(dx, dz)
            if d <= WALL_SENSE_ENTER:
                target = 1.0
            elif d <= WALL_SENSE_EXIT and wall.near_alpha > 0.05:
                target = 1.0
        wall.near_alpha += (target - wall.near_alpha) * min(time.dt * 7.0, 1.0)
        if target == 0.0 and wall.near_alpha < 0.02:
            wall.near_alpha = 0.0
            if wall.mode == Wall.MODE_NEAR:
                wall.set_dark()
            continue
        if wall.mode == Wall.MODE_DARK and wall.near_alpha > 0.04:
            wall.enter_near()
        if wall.mode == Wall.MODE_NEAR:
            wall.apply_near_alpha(wall.near_alpha)

    # ---- 2.5 卡墙保护 ----
    push_out_if_stuck(player)

    # ---- 3. 保险丝：靠近提示 + 10 米脉动/电流声 ----
    nearest_fuse_d = None
    for f in list(FUSES):
        if f.is_dead:
            continue
        d = dist_xz(player.position, f.position)
        f.near = d <= FUSE_SENSE_RANGE
        if nearest_fuse_d is None or d < nearest_fuse_d:
            nearest_fuse_d = d
    # ---- 交互提示：柜子/日记/管子/保险丝（按最近目标动态换文案；含高度判定）----
    prompt_kind, prompt_d = None, 2.0
    for c in list(CABINETS):
        if c.is_dead or abs(player.y - c.y) > 2.2:
            continue
        d = dist_xz(player.position, c.position)
        if d < prompt_d:
            prompt_kind, prompt_d = 'cabinet', d
    for b in list(DIARIES):
        if b.is_dead or abs(player.y - b.y) > 2.2:
            continue
        d = dist_xz(player.position, b.position)
        if d < prompt_d:
            prompt_kind, prompt_d = 'diary', d
    for p in list(PIPES):
        if p.is_dead or abs(player.y - p.y) > 2.2:
            continue
        d = dist_xz(player.position, p.position)
        if d < prompt_d:
            prompt_kind, prompt_d = 'pipe', d
    # ---- ★ 第三关交互提示：门 / 报告 / 门禁卡 / 手术台 / 主控门 ----
    for d in list(DOORS):
        if d.is_dead or abs(player.y - d.y) > 2.2:
            continue                            # ★ 开/关门提示分开显示
        dd = dist_xz(player.position, d.position)
        k = 'door' if not d.open else 'door_open'
        if dd < prompt_d:
            prompt_kind, prompt_d = k, dd
    for rp in list(REPORTS):
        if rp.is_dead or abs(player.y - rp.y) > 2.2:
            continue
        dd = dist_xz(player.position, rp.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'report', dd
    for kc in list(KEYCARDS):
        if kc.is_dead or abs(player.y - kc.y) > 2.2:
            continue
        dd = dist_xz(player.position, kc.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'keycard', dd
    for tb in list(TABLES):
        if tb.is_dead or tb.searched or abs(player.y - tb.y) > 2.2:
            continue
        dd = dist_xz(player.position, tb.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'table', dd
    for tk in list(TANKS):                      # ★ 培养罐搜查提示
        if tk.is_dead or tk.searched or abs(player.y - tk.y) > 2.2:
            continue
        dd = dist_xz(player.position, tk.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'tank', dd
    for dr in list(DRAWERS):
        if dr.is_dead or dr.searched or abs(player.y - dr.y) > 2.2:
            continue
        dd = dist_xz(player.position, dr.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'drawer', dd
    for md in list(MAIN_DOORS):
        if md.is_dead or abs(player.y - md.y) > 2.2:
            continue
        dd = dist_xz(player.position, md.position)
        if dd < prompt_d:
            prompt_kind, prompt_d = 'maindoor', dd
    if nearest_fuse_d is not None and nearest_fuse_d < prompt_d \
            and abs(player.y - 0.7) < 2.2:
        prompt_kind, prompt_d = 'fuse', nearest_fuse_d
    if player.hidden:
        prompt_text.enabled = False             # 柜内提示由窥视遮罩负责
    else:
        # ★ 规格三.3：主控门提示距离同步放宽（3 米），其余交互 1.8 米
        prompt_text.enabled = (prompt_kind is not None
                               and prompt_d < (3.0 if prompt_kind == 'maindoor' else 2.0))
        if prompt_text.enabled:
            prompt_text.text = {
                'cabinet': '— [按 E] 钻入柜子 —',
                'diary': '[按 E] 查看 · [按 R] 拾取',
                'pipe': '— [按 E] 拾取空管子 —',
                'fuse': '— [按 E] 收集保险丝 —',
                'door': '— [按 E] 静音推门（无噪音）—',
                'door_open': '— [按 E] 关上推拉门 —',
                'report': '[按 E] 查看 · [按 R] 拾取',
                'keycard': '— [按 E] 拾取门禁卡 —',
                'table': '— [按 E] 搜查手术台 —',
                'tank': '— [按 E] 搜查培养罐 —',
                'drawer': '— [按 E] 搜查抽屉柜 —',
                'maindoor': '— [按 E] 刷开主控门 —',
            }[prompt_kind]
    if nearest_fuse_d is not None and nearest_fuse_d < FUSE_SENSE_RANGE:
        buzz_timer -= time.dt
        if buzz_timer <= 0:
            buzz_timer = 0.55
            k_f = clamp(1 - nearest_fuse_d / FUSE_SENSE_RANGE, 0, 1)
            play_sfx('buzz', volume=0.08 + 0.22 * k_f,
                     pitch=random.uniform(0.9, 1.1))

    # ---- 4. 出口：真实出口触门通关（含高度判定）；假出口触发伏击 ----
    for gate in list(level_manager.exit_gates):
        if gate is None or gate.is_dead:
            continue
        if dist_xz(player.position, gate.position) < 1.6 \
                and abs(player.y - gate.gate_base_y) < 1.6:
            if gate.is_real:
                if not gate.locked:
                    win_game()
                    return
                elif gate.hint_cd <= 0:
                    gate.hint_cd = 2.5
                    print(f'【出口】绿灯未亮——还差 {FUSES_NEEDED - collected_fuses} 枚保险丝')
            elif not gate.ambushed and not player.hidden:
                trigger_ambush(gate)             # ★ 选错门：伏击！

    # ---- 5. 最近怪物距离 → 危险晕影/发抖 + 全局心跳（音量与频率随距离）----
    nearest_m = None
    for m in list(MONSTERS):
        if m.is_dead:
            continue
        d = dist_xz(m.position, player.position)
        if nearest_m is None or d < nearest_m:
            nearest_m = d
    if nearest_m is not None and nearest_m < DANGER_RANGE:
        danger_k = 1 - clamp((nearest_m - KILL_DISTANCE) /
                             (DANGER_RANGE - KILL_DISTANCE), 0, 1)
    else:
        danger_k = 0.0
    update_vignette(time.dt)
    # ★ 规格二.1/二.2：心跳目标音量 lerp 平滑过渡（绝不瞬间突变）；
    #   心跳为单一循环 Audio 实例（is_heartbeat_playing 守卫，绝不叠加爆音）
    _hb_target = 0.0
    _hb_k = 0.0
    if nearest_m is not None and nearest_m < MONSTER_AUDIO_RANGE:
        _hb_k = clamp(1 - (nearest_m - KILL_DISTANCE) /
                      (MONSTER_AUDIO_RANGE - KILL_DISTANCE), 0, 1)
        _hb_target = 0.15 + 0.75 * _hb_k
    if fear_value[0] > 50.0:
        _hb_target = max(_hb_target, 0.2 + 0.6 * fear_value[0] / 100.0)
    try:
        if heartbeat_audio is not None:
            heartbeat_audio.volume = lerp(heartbeat_audio.volume, _hb_target,
                                          min(time.dt * 4.0, 1.0))
            heartbeat_audio.pitch = lerp(heartbeat_audio.pitch,
                                         0.8 + 0.6 * _hb_k,
                                         min(time.dt * 4.0, 1.0))
            if _hb_target > 0.01 and not is_heartbeat_playing:
                heartbeat_audio.play()
                is_heartbeat_playing = True
    except Exception:
        pass

    # ---- 5.5 ★ 恐怖值（规格三）：最近怪距 <10 米飙升（越近越快）、
    #      >15 米缓慢回落；>50 心跳增强、>80 晕影加重+镜头发抖+急促惊悚音 ----
    if nearest_m is not None and nearest_m < 10.0:
        # ★ 规格四.1：二次曲线——距离越近增长越快（10 米处 0/秒 → 贴脸 70/秒）
        fear_value[0] = min(100.0, fear_value[0] +
                            ((10.0 - nearest_m) / 10.0) ** 1.6 * 70.0 * time.dt)
    elif nearest_m is None or nearest_m > 15.0:
        fear_value[0] = max(0.0, fear_value[0] - 8.0 * time.dt)
    try:
        fear_fill.scale = Vec3(max(0.0001, 0.62 * fear_value[0] / 100.0), 0.02, 1)
    except Exception:
        pass
    if fear_value[0] > 80.0 and player is not None:
        player.camera_pivot.x += math.sin(pytime.time() * 47.0) * 0.012
        player.camera_pivot.y += math.sin(pytime.time() * 39.0) * 0.008
        _fear_scare_timer[0] -= time.dt
        if _fear_scare_timer[0] <= 0:
            _fear_scare_timer[0] = 4.0
            play_random_scare()             # ★ 急促惊悚环境音（远处随机位）

    # ---- 6. 随机环境音（滴水/金属碰撞）----
    ambient_event_timer -= time.dt
    if ambient_event_timer <= 0:
        ambient_event_timer = random.uniform(8.0, 18.0)
        if random.random() < 0.6:
            play_sfx('drip', volume=0.35, pitch=random.uniform(0.9, 1.15))
        else:
            play_sfx('clang', volume=0.30, pitch=random.uniform(0.85, 1.1))

    # ---- ★ 随机惊吓环境音（规格：15~45 秒随机间隔；本闸门只在 PLAYING 推进，
    #        暂停/菜单/死亡状态不计时、不触发）----
    scare_ambience_timer -= time.dt
    if scare_ambience_timer <= 0:
        scare_ambience_timer = random.uniform(*SCARE_AMBIENCE_INTERVAL)
        play_random_scare()

    # ---- 7. 小地图箭头实时绑定玩家朝向 ----
    if minimap_panel.enabled and minimap_arrow is not None:
        minimap_arrow.rotation_z = -player.rotation_y

    # ---- 8. UI：回声冷却提示 ----
    echo_text.text = ('回声：就绪 ◆' if player.echo_cooldown <= 0
                      else f'回声冷却…… {player.echo_cooldown:.1f}s')


def scare_active_global_off():
    global scare_active
    scare_active = False
    if player is not None:
        player.camera_pivot.x = 0.0
        player.camera_pivot.y = player._base_h


def input(key):
    """全局按键处理（按状态机分发）。
    ★ 规格三.1：本函数不会拦截任何鼠标按键——Ursina 的 Button 点击由引擎的
    鼠标射线（mouse.hovered_entity → on_click）独立处理，与本按键分发无关；
    菜单/关卡选择状态下，'left mouse down' 落不到任何分支，直接放行，
    绝不提前 return 吞掉按钮点击。潜行用的"按住左键"只在 PLAYING 分支读取。"""
    # ---- ★ T：全屏 / 半屏窗口切换（规格二，任何状态下均可；原 F11 已替换）----
    if key == 't':
        try:
            if window.fullscreen:
                # 全屏 → 半屏窗口 1280×720 并居中
                # （Panda 的 window.size 回读恒为缓冲分辨率，写 windowed_size 才生效）
                window.fullscreen = False
                window.windowed_size = (1280, 720)
                window.position = (max(0, (window.screen_resolution[0] - 1280) // 2),
                                   max(0, (window.screen_resolution[1] - 720) // 2))
                print('【窗口】已切换为半屏 1280×720')
            else:
                # 窗口 → 全屏 1920×1080
                window.fullscreen = True
                window.windowed_size = (1920, 1080)
                print('【窗口】已切换为全屏 1920×1080')
        except Exception as e:
            print(f'（窗口切换失败：{e}）')
        return

    # ---- Esc：暂停 / 继续 / 关闭子面板 / 返回 ----
    if key == 'escape':
        if game_state == GameState.PLAYING:
            if diary_open:
                close_diary()
            else:
                pause_game()
        elif game_state == GameState.PAUSED:
            resume_game()
        elif game_state in (GameState.DEAD, GameState.WIN):
            open_menu()
        elif game_state == GameState.MENU and lore_read_open:
            close_lore_read()               # 阅读面板 → 回档案库列表
        elif game_state in (GameState.LEVEL_SELECT,) or (
                game_state == GameState.MENU
                and (settings_open or level_select_open or archive_open)):
            open_menu()                     # 关卡选择 / 档案库 / 任意子面板 → 回主菜单
        return

    # ---- E：交互（阅读中优先合上日记）----
    if key == 'e':
        if game_state == GameState.PLAYING and diary_open:
            close_diary()
            return
        if game_state == GameState.PLAYING and player is not None:
            player.try_interact()
        return

    # ---- R：拾取（规格一.3：E 阅读 / R 拾取分离）----
    if key == 'r':
        if game_state == GameState.PLAYING and player is not None and not diary_open:
            player.try_pickup_readable()
        return

    # ---- 仅 PLAYING：右键回声 / F 投掷 / ★ Q 屏息（按下与松开事件）----
    if game_state == GameState.PLAYING and player is not None:
        if key == 'right mouse down':           # 鼠标右键：敲击地面/回声探测
            player.try_echo()
        elif key == 'f':
            player.throw_item()
        elif key == 'q':                        # ★ Q 按下：开始屏息（规格写法）
            if player.o2_exhaust > 0:
                print('【屏息】你还在疲惫期，喘不上气……')
            elif player.oxygen <= 0:
                player.is_holding_breath = False
            else:
                player.is_holding_breath = True
                print('（你屏住了呼吸……）')
        elif key == 'q up':                     # ★ Q 松开：结束屏息
            player.is_holding_breath = False
        return

    # ---- 暂停 / GAME OVER / 胜利：R 重开当前关，Q 回主菜单 ----
    if game_state in (GameState.PAUSED, GameState.DEAD, GameState.WIN):
        if key == 'r':
            start_level(current_level)
        elif key == 'q':
            open_menu()


# =====================================================================================
#  启动
# =====================================================================================
random.seed(pytime.time())
load_save()                     # 读取设置
load_fragment_data()            # ★ 规格一.3：读取 save_data.json（碎片进度）
level_manager = LevelManager()
build_all_ui()
build_minimap()
build_overlays()
show_group('menu')
apply_mouse_state()             # ★ 规格二.1：启动即进入菜单鼠标状态（解锁+可见）

print('=' * 60)
print('  BLIND HORROR · 暗夜回声（柜内窥视 · 楼梯 · 屏息修复版）')
print('  你是盲女伊芙琳，被困于废弃的地下研究所。收集日记，寻找真相。')
_amb_ok = '✓' if ambient_light is not None else '✗'
_lit_ok = '✓' if lit_shader is not None else '✗'
_model_ok = 'models/model_monster.obj' if MONSTER_OBJ_PATH else '组合人形（黑细身体+红眼）'
print(f'  光照：环境光{_amb_ok} + 玩家点光 | lit shader：{_lit_ok} | 近平面 0.05')
print(f'  怪物模型：{_model_ok} | 碎片存档：{len(collected_fragment_ids)}/50')
print('  请戴上耳机——3D 声效、屏息与心跳都在等你。')
print('=' * 60)

app.run()
