"""
康神语录 Bot — for the 「康神开播了」 server
功能:
  /语录            随机发一条康神语录 (漂亮的 embed 卡片)
  /语录 关键词     按关键词搜一条
  !语录 / 康神语录  文字版触发 (同样随机一条)
  /加语录 内容     加一条新语录 (仅服主/管理员)
  /删语录 编号     删一条 (仅服主/管理员, 编号看 /语录列表)
  /语录列表        看全部语录和编号
  /语录条数        现在总共多少条

语音 (voice channel):
  /语音语录        进你所在的语音频道, 出声朗读一条随机语录
  /语音语录 关键词 按关键词挑一条读
  !语音语录        文字版语音触发
  /进来            只进语音频道, 不说话
  /离开            离开语音频道
  /说 内容         让 bot 在语音频道说任意一句话 (仅服主/管理员, 防乱用)

  原声优先: clips/ 里放 001.mp3、002.mp3... (编号 = 语录列表编号),
  有原声片段的语录直接放原声, 没有的才用 TTS 合成朗读。
  TTS 音色: 环境变量 TTS_VOICE, 默认 zh-CN-YunxiNeural (年轻男声);
  可换 zh-CN-YunyangNeural (男声播音) / zh-CN-XiaoxiaoNeural (女声) 等。

语录存 quotes.json, 加/删会立刻存盘, 不用改代码、不用重启。
Token 只从环境变量 DISCORD_TOKEN 读, 绝不写进代码。
语音播放需要系统装 ffmpeg。
"""
import asyncio
import json
import os
import random
import tempfile
from pathlib import Path

import discord
from discord import app_commands

try:
    import edge_tts
except ImportError:  # 没装 edge-tts 时文字功能照常, 语音功能会给出提示
    edge_tts = None

DATA_FILE = Path(__file__).with_name("quotes.json")
CLIPS_DIR = Path(__file__).with_name("clips")

import shutil


def ffmpeg_exe() -> str:
    """找 ffmpeg: 先用系统的, 没有就用 imageio-ffmpeg 自带的 (Mac 没装 ffmpeg 时兜底)。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-YunxiNeural")
TTS_RATE = os.environ.get("TTS_RATE", "+0%")

# 每个服务器一把播放锁, 防止两条语录同时抢着说话
_play_locks: dict[int, asyncio.Lock] = {}


def play_lock(guild_id: int) -> asyncio.Lock:
    return _play_locks.setdefault(guild_id, asyncio.Lock())


def load_quotes() -> list[str]:
    if not DATA_FILE.exists():
        return []
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [str(q).strip() for q in data if str(q).strip()]
    except Exception:
        return []


def save_quotes(quotes: list[str]) -> None:
    DATA_FILE.write_text(
        json.dumps(quotes, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pick_quote(keyword: str = ""):
    """返回 (编号, 文本) 或 None; 编号从 0 开始。"""
    quotes = load_quotes()
    if not quotes:
        return None
    pool = list(enumerate(quotes))
    if keyword:
        pool = [(i, q) for i, q in pool if keyword in q]
        if not pool:
            return None
    return random.choice(pool)


def clip_for(idx: int) -> Path | None:
    """语录编号 (0开始) 对应的原声音频, 如 clips/001.mp3, 没有返回 None。"""
    for suffix in (".mp3", ".wav", ".ogg", ".m4a", ".opus"):
        p = CLIPS_DIR / f"{idx + 1:03d}{suffix}"
        if p.exists():
            return p
    return None


async def tts_to_file(text: str) -> Path:
    """用 edge-tts 把一句话合成 mp3 临时文件, 返回路径 (调用方负责删)。"""
    if edge_tts is None:
        raise RuntimeError("edge-tts 未安装, 先 pip install -r requirements.txt")
    fd, name = tempfile.mkstemp(suffix=".mp3", prefix="kangshen-tts-")
    os.close(fd)
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(name)
    return Path(name)


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient | None:
    """让 bot 进到命令使用者所在的语音频道; 使用者不在语音频道时返回 None。"""
    voice_state = interaction.user.voice
    if voice_state is None or voice_state.channel is None:
        return None
    channel = voice_state.channel
    vc = interaction.guild.voice_client
    if vc is not None and vc.is_connected():
        if vc.channel != channel:
            await vc.move_to(channel)
        return vc
    return await channel.connect()


async def speak_in_voice(vc: discord.VoiceClient, idx: int | None, text: str) -> str:
    """
    在语音频道里播放一条语录: 有原声放原声, 没有用 TTS。
    返回实际用的方式: '原声' 或 'TTS'。会等播放结束再返回。
    """
    async with play_lock(vc.guild.id):
        tmp: Path | None = None
        clip = clip_for(idx) if idx is not None else None
        if clip is not None:
            source_path, mode = clip, "原声"
        else:
            tmp = await tts_to_file(text)
            source_path, mode = tmp, "TTS"
        try:
            if vc.is_playing():
                vc.stop()
            done = asyncio.Event()
            loop = asyncio.get_running_loop()
            def _after(err):
                if err is not None:
                    print(f"语音播放出错: {err}")
                loop.call_soon_threadsafe(done.set)

            conn = vc._connection
            if getattr(conn, "dave_protocol_version", 0) > 0 and not getattr(conn, "can_encrypt", False):
                for _ in range(60):  # 最多等 3 秒让 DAVE E2EE 握手完成
                    if getattr(conn, "can_encrypt", False):
                        break
                    await asyncio.sleep(0.05)
            vc.play(
                discord.FFmpegPCMAudio(str(source_path), executable=ffmpeg_exe()),
                after=_after,
            )
            await done.wait()
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        return mode


def quote_embed(text: str, idx: int | None = None, total: int | None = None):
    embed = discord.Embed(
        title="🎙️ 康神语录",
        description=f"「{text}」",
        color=discord.Color.gold(),
    )
    footer = "— 康神"
    if idx is not None and total:
        footer += f"  ·  第 {idx + 1} / {total} 条"
    embed.set_footer(text=footer)
    return embed


intents = discord.Intents.default()
intents.message_content = True  # 需要在 Developer Portal 里也打开 Message Content Intent
intents.voice_states = True

# macOS 上 discord.py 经常找不到系统 Opus 库 (报错 OpusNotLoaded):
# 优先加载随 bot 附带的 libopus.0.dylib, 没有再找系统里的
if not discord.opus.is_loaded():
    import ctypes.util
    _opus_candidates = [
        str(Path(__file__).with_name("libopus.0.dylib")),
        str(Path(__file__).with_name("libopus.dylib")),
        ctypes.util.find_library("opus"),
        "libopus.0.dylib",
        "opus",
    ]
    for _cand in _opus_candidates:
        if not _cand:
            continue
        try:
            discord.opus.load_opus(_cand)
            print(f"opus loaded: {_cand}")
            break
        except Exception:
            pass
    if not discord.opus.is_loaded():
        print("WARNING: opus 库没加载成功, 语音频道播放会失败 (OpusNotLoaded)")

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def quote_payload(idx: int, text: str) -> dict:
    """发语录用的参数: 卡片 + (有原声的话) 把音频文件也发到文字频道, 点开就能听。"""
    payload: dict = {"embed": quote_embed(text, idx, len(load_quotes()))}
    clip = clip_for(idx)
    if clip is not None:
        payload["file"] = discord.File(clip, filename=f"康神语录-{idx + 1:03d}.mp3")
    return payload


def is_manager(interaction: discord.Interaction) -> bool:
    return (
        interaction.user == interaction.guild.owner
        or interaction.user.guild_permissions.administrator
        or interaction.user.guild_permissions.manage_messages
    )


async def quote_autocomplete(interaction: discord.Interaction, current: str):
    """关键词输入框的自动补全: 把语录列出来点选, 不用记原文。"""
    quotes = load_quotes()
    if current:
        matches = [q for q in quotes if current in q]
    else:
        matches = quotes
    return [app_commands.Choice(name=q[:100], value=q) for q in matches[:25]]


@tree.command(name="语录", description="随机来一条康神语录，或按关键词搜")
@app_commands.describe(关键词="可选, 比如: 开播 / 瓦 / 上分")
async def random_quote(interaction: discord.Interaction, 关键词: str = ""):
    picked = pick_quote(关键词)
    if picked is None:
        msg = "语录库还是空的呀, 先用 /加语录 加一条吧~" if not 关键词 else f"没有包含「{关键词}」的语录呢"
        await interaction.response.send_message(msg, ephemeral=True)
        return
    idx, text = picked
    await interaction.response.send_message(**quote_payload(idx, text))


@tree.command(name="语音语录", description="进语音频道, 出声读一条康神语录 (先自己进一个语音频道)")
@app_commands.describe(关键词="可选, 比如: 开播 / 瓦 / 上分")
async def voice_quote(interaction: discord.Interaction, 关键词: str = ""):
    picked = pick_quote(关键词)
    if picked is None:
        msg = "语录库还是空的呀, 先用 /加语录 加一条吧~" if not 关键词 else f"没有包含「{关键词}」的语录呢"
        await interaction.response.send_message(msg, ephemeral=True)
        return
    # 语音合成可能要几秒, 先 defer 免得交互超时
    await interaction.response.defer()
    vc = await ensure_voice(interaction)
    if vc is None:
        await interaction.followup.send("你先自己进一个语音频道, 我才知道去哪儿说呀~", ephemeral=True)
        return
    idx, text = picked
    await interaction.followup.send(**quote_payload(idx, text))
    try:
        mode = await speak_in_voice(vc, idx, text)
        if mode == "TTS" and clip_for(idx) is None:
            pass  # 正常 TTS, 不用额外说明
    except Exception as e:
        await interaction.followup.send(f"语音没放出来: {type(e).__name__}: {e}", ephemeral=True)


@tree.command(name="进来", description="让 bot 进你所在的语音频道 (不说话)")
async def join_voice(interaction: discord.Interaction):
    vc = await ensure_voice(interaction)
    if vc is None:
        await interaction.response.send_message("你先自己进一个语音频道呀~", ephemeral=True)
        return
    await interaction.response.send_message(f"来啦, 我在 **{vc.channel.name}** 里待着了, 发 /语音语录 我就开口")


@tree.command(name="离开", description="让 bot 离开语音频道")
async def leave_voice(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc is None or not vc.is_connected():
        await interaction.response.send_message("我现在没在语音频道里呢", ephemeral=True)
        return
    await vc.disconnect()
    await interaction.response.send_message("走啦, 想听语录再喊我~")


@tree.command(name="说", description="让 bot 在语音频道说一句话 (仅服主/管理员)")
@app_commands.describe(内容="要它说的话")
async def say_text(interaction: discord.Interaction, 内容: str):
    if not is_manager(interaction):
        await interaction.response.send_message("这个只有服主/管理员能用哦, 不然谁都能让它乱说话啦", ephemeral=True)
        return
    await interaction.response.defer()
    vc = await ensure_voice(interaction)
    if vc is None:
        await interaction.followup.send("你先自己进一个语音频道呀~", ephemeral=True)
        return
    text = 内容.strip()
    quotes = load_quotes()
    idx = quotes.index(text) if text in quotes else None
    try:
        mode = await speak_in_voice(vc, idx, text)
        note = "原声" if mode == "原声" else "合成音"
        await interaction.followup.send(f"说啦 ({note}): 「{text}」", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"语音没放出来: {type(e).__name__}: {e}", ephemeral=True)


@tree.command(name="加语录", description="加一条康神语录 (服主/管理员)")
@app_commands.describe(内容="语录原文, 不用加引号")
async def add_quote(interaction: discord.Interaction, 内容: str):
    if not is_manager(interaction):
        await interaction.response.send_message("这个只有服主/管理员能用哦", ephemeral=True)
        return
    text = 内容.strip()
    if not text:
        return
    quotes = load_quotes()
    if text in quotes:
        await interaction.response.send_message("这条已经在语录库里啦", ephemeral=True)
        return
    quotes.append(text)
    save_quotes(quotes)
    await interaction.response.send_message(embed=quote_embed(text, len(quotes) - 1, len(quotes)))


@tree.command(name="删语录", description="按编号删一条语录 (服主/管理员)")
@app_commands.describe(编号="在 /语录列表 里看到的编号, 从 1 开始")
async def delete_quote(interaction: discord.Interaction, 编号: int):
    if not is_manager(interaction):
        await interaction.response.send_message("这个只有服主/管理员能用哦", ephemeral=True)
        return
    quotes = load_quotes()
    if not (1 <= 编号 <= len(quotes)):
        await interaction.response.send_message(f"编号不对, 现在只有 1–{len(quotes)}", ephemeral=True)
        return
    removed = quotes.pop(编号 - 1)
    save_quotes(quotes)
    await interaction.response.send_message(f"删掉啦: 「{removed}」", ephemeral=True)


@tree.command(name="语录列表", description="查看全部语录和编号")
async def list_quotes(interaction: discord.Interaction):
    quotes = load_quotes()
    if not quotes:
        await interaction.response.send_message("语录库还是空的呀", ephemeral=True)
        return
    lines = [f"{i + 1}. {q}" for i, q in enumerate(quotes)]
    chunk = ""
    await interaction.response.send_message("📜 **康神语录列表**", ephemeral=True)
    for line in lines:
        if len(chunk) + len(line) + 1 > 1800:
            await interaction.followup.send(chunk, ephemeral=True)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await interaction.followup.send(chunk, ephemeral=True)


@tree.command(name="语录条数", description="语录库现在有多少条")
async def count_quotes(interaction: discord.Interaction):
    await interaction.response.send_message(f"现在一共有 **{len(load_quotes())}** 条康神语录")


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user} — quotes loaded: {len(load_quotes())}, TTS voice: {TTS_VOICE}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content = message.content.strip()
    # 文字触发: !语录 / 康神语录 / 来句康神的
    if content in ("!语录", "康神语录", "来句康神的", "康神说"):
        picked = pick_quote()
        if picked:
            idx, text = picked
            await message.channel.send(**quote_payload(idx, text))
        return
    # 语音触发: !语音语录 — 发消息的人必须在语音频道里
    if content in ("!语音语录", "语音语录", "康神说一句"):
        picked = pick_quote()
        if not picked:
            return
        if message.author.voice is None or message.author.voice.channel is None:
            await message.channel.send("你先自己进一个语音频道, 我才知道去哪儿说呀~")
            return
        idx, text = picked
        await message.channel.send(**quote_payload(idx, text))
        vc = message.guild.voice_client
        if vc is None or not vc.is_connected():
            vc = await message.author.voice.channel.connect()
        elif vc.channel != message.author.voice.channel:
            await vc.move_to(message.author.voice.channel)
        try:
            await speak_in_voice(vc, idx, text)
        except Exception as e:
            await message.channel.send(f"语音没放出来: {type(e).__name__}: {e}")


# 关键词参数自动补全 (两个命令共用)
random_quote.autocomplete("关键词")(quote_autocomplete)
voice_quote.autocomplete("关键词")(quote_autocomplete)
say_text.autocomplete("内容")(quote_autocomplete)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("缺少 DISCORD_TOKEN 环境变量 — 看 README 的步骤, 不要把 token 写进代码/发到聊天里")
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus("libopus.so.0")
        except Exception:
            pass  # 多数环境 discord.py[voice] 会自带/自动加载, 进频道失败时再排查
    client.run(token)
