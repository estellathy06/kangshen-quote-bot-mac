# 康神语录 Bot

给「康神开播了」服务器用的自制 Discord bot, 专门发康神语录 — 文字版 + 语音版都有。

## 功能
### 文字
- `/语录` 随机一条, `/语录 关键词` 按关键词搜一条 — 都是金色 embed 卡片
- 文字触发: 在频道里发 `!语录` / `康神语录` / `来句康神的` 也会回一条
- `/加语录 内容`、`/删语录 编号` — 仅服主/管理员, 立刻存盘不用重启
- `/语录列表`、`/语录条数`

### 语音 (voice channel)
- `/语音语录` — 你先自己进一个语音频道, bot 会跟进来, 出声读一条随机语录, 同时在文字频道发同一条卡片; `/语音语录 关键词` 按关键词挑一条读; 文字发 `!语音语录` 也行
- `/进来` bot 只进语音频道待着, `/离开` 让它走
- `/说 内容` — 让 bot 在语音频道说任意一句话, **仅服主/管理员** (防别人让它乱说话)
- **原声优先**: 把康神原声音频放进 `clips/`, 文件名 = 语录编号三位数 (如 `001.mp3` = 第 1 条)。有原声的语录直接放原声, 没有的才用 TTS 读
- **TTS 音色**: 默认 `zh-CN-YunxiNeural` (年轻男声)。换音色改环境变量 `TTS_VOICE`, 可选如 `zh-CN-YunyangNeural` (男声播音腔)、`zh-CN-XiaoxiaoNeural` (女声); 语速 `TTS_RATE` 如 `+10%`
- 读完不会自动退出, 会待在频道里等下一条, 不想听了发 `/离开`
- 语音需要: 系统装了 `ffmpeg`, 且 bot 邀请权限包含 Connect / Speak (见下面步骤 3)

## 上线步骤 (只需做一次)
1. 去 Discord Developer Portal (discord.com/developers/applications) → New Application
   → 名字填「康神语录」→ Bot 页点 Reset Token 拿到 token
   ⚠️ token 只能填到运行机器的环境变量里, 绝不发到聊天、截图、GitHub
2. Bot 页打开这三个开关: Presence / Server Members / **Message Content Intent**
3. OAuth2 → URL Generator → 勾 `bot` + `applications.commands`
   → Bot Permissions 勾 Send Messages / Embed Links / Read Message History / **Connect / Speak / Use Voice Activity**
   → 用生成的链接把 bot 邀请进「康神开播了」
   (如果 bot 已经用旧链接进服了: 用新链接重新邀请一次, 权限才会补上语音部分, 不用踢出去)
4. 运行 (运行机器要装 ffmpeg):
   ```bash
   pip install -r requirements.txt
   DISCORD_TOKEN=你的token python bot.py
   # 换音色示例: TTS_VOICE=zh-CN-YunyangNeural DISCORD_TOKEN=... python bot.py
   ```
   长期挂着: 可以放自己的电脑/小服务器, 或 Railway / Render 等托管。
5. 灌语录: 把语录一条条发给 Muse 批量写入 quotes.json, 或进服后用 `/加语录` 一条条加。
   原声片段: 把音频文件发给 Muse, 说清对应哪条语录, 帮你改名放进 `clips/`。

## 文件
- `bot.py` 主程序
- `quotes.json` 语录库 (纯文本数组, 可直接编辑)
- `clips/` 原声音频 (编号命名, 可选)
