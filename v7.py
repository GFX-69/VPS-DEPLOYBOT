import random
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
import time
import re
import socket  
import asyncssh  
from aiohttp import web

# Configuration
TOKEN = os.getenv('DISCORD_BOT_TOKEN') or 'YOUR_FALLBACK_TOKEN_HERE'
RAM_LIMIT = '2g'
SERVER_LIMIT = 122
LOGS_CHANNEL_ID = 1514847215271673896  
ADMIN_ROLE_ID = 1477997687532945478      

database_file = 'database.txt'
admin_file = 'admins.txt'

# ==================== CLUSTER NODE CONFIGURATION ====================
NODES = {
    "node1": {
        "host": "botnode1.cryzoncloud.qzz.io",
        "port": 22,                            
        "username": "root",
        "password": os.getenv('NODE_1_PASSWORD') or 'NODE_1_PASSWORD_HERE',  
        "client_keys": None                  
    },
    "node2": {
        "host": "botnode2.cryzoncloud.qzz.io",
        "port": 22,                            
        "username": "root",
        "password": os.getenv('NODE_2_PASSWORD') or 'NODE_2_PASSWORD_HERE',  
        "client_keys": None                  
    },
    "node3": {
        "host": "botnode3.cryzoncloud.qzz.io",
        "port": 22,                            
        "username": "root",
        "password": os.getenv('NODE_3_PASSWORD') or 'NODE_3_PASSWORD_HERE',  
        "client_keys": None                  
    },
    "node4": {
        "host": "botnode4.cryzoncloud.qzz.io",
        "port": 22,                            
        "username": "root",
        "password": os.getenv('NODE_4_PASSWORD') or 'NODE_4_PASSWORD_HERE',  
        "client_keys": None                  
    },
    "node5": {
        "host": "botnode5.cryzoncloud.qzz.io",
        "port": 22,                            
        "username": "root",
        "password": os.getenv('NODE_5_PASSWORD') or 'NODE_5_PASSWORD_HERE',  
        "client_keys": None                  
    }
}

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True  

bot = commands.Bot(command_prefix='/', intents=intents)
EMBED_COLOR = 0x9B59B6  

OS_OPTIONS = {
    "ubuntu": {"image": "ubuntu24-systemd", "name": "Ubuntu 24.04 (Systemd)", "emoji": "🐧", "description": "Custom Ubuntu 24.04 with systemd support"},
    "debian": {"image": "debian-vps", "name": "Debian 12", "emoji": "🦕", "description": "Rock-solid stability with large software repository"},
    "alpine": {"image": "alpine-vps", "name": "Alpine Linux", "emoji": "⛰️", "description": "Lightweight and security-focused"},
    "arch": {"image": "arch-vps", "name": "Arch Linux", "emoji": "🎯", "description": "Rolling release with bleeding-edge software"},
    "kali": {"image": "kali-vps", "name": "Kali Linux", "emoji": "💣", "description": "Penetration testing and security auditing"},
    "fedora": {"image": "fedora-vps", "name": "Fedora", "emoji": "🎩", "description": "Innovative features with Red Hat backing"}
}

LOADING_ANIMATION = ["🔄", "⚡", "✨", "🌀", "🌪️", "🌈"]
SUCCESS_ANIMATION = ["✅", "🎉", "✨", "🌟", "💫", "🔥"]
ERROR_ANIMATION = ["❌", "💥", "⚠️", "🚨", "🔴", "🛑"]
DEPLOY_ANIMATION = ["🚀", "🛰️", "🌌", "🔭", "👨‍🚀", "🪐"]

# ==================== REMOTE SSH UTILITY ====================
async def run_node_command(node_key, command):
    if node_key not in NODES:
        raise ValueError(f"Node '{node_key}' is not configured in the cluster map.")
    
    cfg = NODES[node_key]
    try:
        async with asyncssh.connect(cfg["host"], port=cfg.get("port", 22), username=cfg["username"], 
                                    password=cfg["password"], client_keys=cfg["client_keys"], known_hosts=None, 
                                    keepalive_interval=10, keepalive_count_max=3) as conn:
            result = await conn.run(command, check=False)
            return result.exit_status, result.stdout, result.stderr
    except asyncssh.PermissionDenied as auth_err:
        raise RuntimeError(f"SSH Auth Failed on {node_key.upper()}. Please verify configuration.") from auth_err

async def open_node_process(node_key, command):
    if node_key not in NODES:
        raise ValueError(f"Node '{node_key}' is not configured in the cluster map.")
    
    cfg = NODES[node_key]
    try:
        conn = await asyncssh.connect(cfg["host"], port=cfg.get("port", 22), username=cfg["username"], 
                                     password=cfg["password"], client_keys=cfg["client_keys"], known_hosts=None, 
                                     keepalive_interval=10, keepalive_count_max=3)
        process = await conn.create_process(command)
        return conn, process
    except asyncssh.PermissionDenied as auth_err:
        raise RuntimeError(f"SSH Auth Failed on {node_key.upper()}. Please verify configuration.") from auth_err

# ==================== WEB SERVER & NODE TUNNEL ====================
async def handle_tunnel_ping(request):
    host_header = request.headers.get('Host', '')
    system_host = socket.gethostname()
    
    if "botnode1" in host_header or "node1" in system_host.lower():
        node_signature = "🟢 Node 1: botnode1.cryzoncloud.qzz.io - Operational"
    else:
        node_signature = f"🟢 Cluster Node ({system_host}) - Operational"

    status_payload = {
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "node": node_signature,
        "tunnel_endpoint": "http://localhost:8080"
    }
    return web.json_response(status_payload)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_tunnel_ping)
    app.router.add_get('/health', handle_tunnel_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌍 Tunnel server securely listening on http://localhost:8080 for node traffic routing.")

# ==================== DATABASE & HELPER UTILITIES ====================
async def is_admin(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    if any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles):
        return True
    if os.path.exists(admin_file):
        with open(admin_file, 'r') as f:
            admins = [line.strip() for line in f.readlines()]
            if str(interaction.user.id) in admins:
                return True
    return False

def get_database_mapping():
    mapping = {}
    if not os.path.exists(database_file):
        return mapping
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 2:
                mapping[parts[1].strip()] = parts[0].strip()
    return mapping

def add_to_database(user, container_name, connection_info, status="Active", node="node1"):
    with open(database_file, 'a') as f:
        f.write(f"{user}|{container_name}|{connection_info}|{status}|{node}\n")

def update_database_status(container_id, new_status):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) >= 2 and parts[1].startswith(container_id):
                while len(parts) < 5:
                    parts.append("node1")
                f.write(f"{parts[0]}|{parts[1]}|{parts[2]}|{new_status}|{parts[4]}\n")
            else:
                f.write(line)

def update_database_connection(container_id, new_conn_str):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) >= 2 and parts[1].startswith(container_id):
                while len(parts) < 5:
                    parts.append("node1")
                f.write(f"{parts[0]}|{parts[1]}|{new_conn_str}|{parts[3]}|{parts[4]}\n")
            else:
                f.write(line)

def remove_from_database_by_id(container_id):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) >= 2 and not parts[1].startswith(container_id):
                f.write(line)

async def capture_ssh_session_line(process):
    try:
        async with asyncio.timeout(15):
            while True:
                output = await process.stdout.readline()
                if not output:
                    break
                output = output.strip()
                if "ssh session:" in output:
                    return output.split("ssh session:")[1].strip()
    except Exception as e:
        print(f"Error capturing SSH: {e}")
    return None

async def capture_sshx_link(process):
    try:
        async with asyncio.timeout(15):
            while True:
                output = await process.stdout.readline()
                if not output:
                    break
                output = output.strip()
                match = re.search(r'(https://sshx\.io/s/[^\s\x1b]+)', output)
                if match:
                    return match.group(1)
    except Exception as e:
        print(f"Error capturing sshx: {e}")
    return None

async def animate_message(interaction: discord.Interaction, message, embed, animation_frames, duration=5):
    start_time = time.time()
    frame_index = 0
    while time.time() - start_time < duration:
        embed.set_author(name=f"{animation_frames[frame_index]} {message}")
        try:
            await interaction.edit_original_response(embed=embed)
        except discord.NotFound:
            break  
        except Exception:
            pass
        frame_index = (frame_index + 1) % len(animation_frames)
        await asyncio.sleep(0.5)

@bot.event
async def on_ready():
    if not change_status.is_running():
        change_status.start()
    
    if not miner_protection_loop.is_running():
        miner_protection_loop.start()
        
    bot.loop.create_task(start_web_server())
    print(f'✨ Bot is ready. Logged in as {bot.user} ✨')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands completely.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tasks.loop(seconds=2)
async def change_status():
    try:
        instance_count = len(open(database_file).readlines()) if os.path.exists(database_file) else 0
        statuses = [
            f"🖥️ {instance_count} VPS Instances Running",
            f"⚡ Hosting {instance_count} Active Virtual Servers",
            f"🚀 VPS Cluster: Online",
            f"💾 Virtualization Engine: Healthy",
            f"🌐 Network Uplink: Stable"
        ]
        await bot.change_presence(
            activity=discord.CustomActivity(name=random.choice(statuses)),
            status=discord.Status.dnd
        )  
    except Exception:
        pass

# ==================== AUTOMATED ANTI-MINER PROTECTOR LOOP ====================
@tasks.loop(seconds=30)
async def miner_protection_loop():
    if not os.path.exists(database_file) or os.path.getsize(database_file) == 0:
        return

    active_instances = []
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 5 and parts[3] == "Active":
                active_instances.append({
                    "owner": parts[0],
                    "container_id": parts[1],
                    "node": parts[4]
                })

    nodes_to_scan = {}
    for inst in active_instances:
        nodes_to_scan.setdefault(inst["node"], []).append(inst)

    mining_signature_regex = re.compile(r'(xmrig|minerd|cryptonight|stratum\+tcp|cpuminer|ethminer)', re.IGNORECASE)

    for node_key, containers in nodes_to_scan.items():
        try:
            for container in containers:
                c_id = container["container_id"]
                exit_code, stdout, stderr = await run_node_command(node_key, f"docker exec {c_id} ps aux")
                if exit_code != 0:
                    continue 
                
                if mining_signature_regex.search(stdout):
                    await run_node_command(node_key, f"docker network disconnect bridge {c_id}")
                    await run_node_command(node_key, f"docker stop {c_id}")
                    update_database_status(c_id, "Suspended")
                    
                    logs_channel = bot.get_channel(LOGS_CHANNEL_ID)
                    if logs_channel:
                        embed = discord.Embed(
                            title="🚨 Anti-Miner Security Action Triggered", 
                            color=0xFF0000, 
                            timestamp=datetime.utcnow()
                        )
                        embed.add_field(name="Target Instance ID", value=f"`{c_id[:12]}`", inline=True)
                        embed.add_field(name="Cluster Node", value=f"`{node_key.upper()}`", inline=True)
                        embed.add_field(name="Allocated Client Reference", value=f"`{container['owner']}`", inline=True)
                        embed.add_field(name="Violation Detected", value="```Illegal crypto mining script signature matched (xmrig/minerd framework)```", inline=False)
                        embed.add_field(name="Resolution State", value="Container pipeline isolated immediately (Network bridge detached, process halted). State set to Suspended.", inline=False)
                        await logs_channel.send(embed=embed)
                        
        except Exception as scan_err:
            print(f"Error executing security check loop on {node_key.upper()}: {scan_err}")

# ==================== GENERAL INFO COMMANDS ====================

@bot.tree.command(name="help", description="📋 Show complete usage guidelines and command indexes | Made by DevaByss")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="✨ VPS Cloud Management Dashboard Engine", description="Welcome to the terminal interface panel.", color=EMBED_COLOR)
    
    user_cmds = (
        "`/list` - Review all structural cloud configurations allocated to you.\n"
        "`/nodes` - Review direct physical cluster metrics and host node health.\n"
        "`/start` - Power-on your engine node and rebind tunnel sessions.\n"
        "`/stop` - Safely halt running container frameworks and processes.\n"
        "`/rebuild` - Factory reset your cloud block to clear data logs.\n"
        "`/regen_ssh` - Generate fresh remote access routes straight to DMs.\n"
        "`/status` - View local cloud metrics, performance data limits, and status states."
    )
    embed.add_field(name="🚀 General User Utilities", value=user_cmds, inline=False)

    admin_cmds = (
        "`/deploy` - Deploy a customized VPS architecture image node for a client.\n"
        "`/admin_list` - Complete cluster inspection showing counts and running IDs across all nodes.\n"
        "`/vps_suspend` - Sever target pipeline network link states immediately.\n"
        "`/vps_unsuspend` - Restore core network bridge pathways.\n"
        "`/vps_delete` - Permanently destroy and wipe a user container completely.\n"
        "`/admin_add` / `/admin_remove` - Modify script admin permission flags."
    )
    embed.add_field(name="👑 Administrative Infrastructure Actions", value=admin_cmds, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="status", description="📊 Inspect active framework run states and configuration limits | Made by DevaByss")
async def status_command(interaction: discord.Interaction):
    user = str(interaction.user)
    my_instances = 0
    total_instances = 0
    
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                total_instances += 1
                if line.strip().split('|')[0] == user:
                    my_instances += 1

    embed = discord.Embed(title="📊 Cloud Cluster System Status", color=EMBED_COLOR)
    embed.add_field(name="📦 Your Active Allocations", value=f"`{my_instances}` Instances Active", inline=True)
    embed.add_field(name="🌍 Total Cluster Loads", value=f"`{total_instances} / {SERVER_LIMIT}` Slots Occupied", inline=True)
    embed.add_field(name="🛠️ Hardware Profiles Assigned", value=f"```RAM Limit: {RAM_LIMIT} per container\nConfigured Nodes: {len(NODES)} Total Nodes```", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="nodes", description="🌐 Query metrics and resource status flags for cluster nodes")
@app_commands.describe(node_choice="Select node to query (node1 to node5)")
@app_commands.choices(node_choice=[
    app_commands.Choice(name="Node 1", value="node1"),
    app_commands.Choice(name="Node 2", value="node2"),
    app_commands.Choice(name="Node 3", value="node3"),
    app_commands.Choice(name="Node 4", value="node4"),
    app_commands.Choice(name="Node 5", value="node5")
])
async def nodes_command(interaction: discord.Interaction, node_choice: str = "node1"):
    await interaction.response.defer(ephemeral=False)
    
    embed = discord.Embed(
        title="🌐 Node Infrastructure Status Engine", 
        description=f"Establishing analytical pipeline connection to {node_choice.upper()} architecture...", 
        color=EMBED_COLOR
    )
    msg = await interaction.followup.send(embed=embed)
    
    try:
        metric_cmd = (
            "echo $(docker ps -q | wc -l) && "
            "echo $(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}')% && "
            "echo $(free -m | awk '/Mem:/ {printf \"%.2f%% used (%dMB/%dMB)\", $3/$2*100, $3, $2}') && "
            "echo $(df -h / | awk 'NR==2 {print $5 \" used (\" $3 \"/\" $2 \")\"}')"
        )
        
        exit_code, stdout, stderr = await run_node_command(node_choice, metric_cmd)
        
        if exit_code == 0:
            metrics = stdout.strip().split('\n')
            running_vps = metrics[0] if len(metrics) > 0 else "0"
            cpu_usage = metrics[1] if len(metrics) > 1 else "Unknown"
            ram_usage = metrics[2] if len(metrics) > 2 else "Unknown"
            disk_usage = metrics[3] if len(metrics) > 3 else "Unknown"
            
            embed.description = f"### 🟢 {node_choice.upper()} Architecture Health Profile"
            embed.clear_fields()
            
            embed.add_field(name="⚡ Operating Status", value="`Online / Operational`", inline=True)
            embed.add_field(name="🧠 CPU Load State", value=f"`{cpu_usage}`", inline=True)
            embed.add_field(name="💾 RAM Usage State", value=f"`{ram_usage}`", inline=True)
            embed.add_field(name="💽 System Disk State", value=f"`{disk_usage}`", inline=True)
            
            embed.add_field(name="📦 Active VPSs", value=f"`{running_vps}` Container Environments", inline=False)
        else:
            raise Exception(stderr.strip())
            
    except Exception as err:
        embed.description = f"### ❌ {node_choice.upper()} Runtime System Failure"
        embed.clear_fields()
        embed.add_field(name="⚡ Operating Status", value="`Unreachable / Offline`", inline=False)
        embed.add_field(name="🚨 Structural Core Connection Error", value=f"```\n{str(err)[:200]}\n```", inline=False)
            
    embed.set_footer(text=f"Cluster Scan Completed • {datetime.now().strftime('%H:%M:%S')}")
    await msg.edit(embed=embed)

# ==================== GENERAL USER VPS CONTROL COMMANDS ====================

@bot.tree.command(name="list", description="📋 View all cloud instances currently registered to you | Made by DevaByss")
async def user_list(interaction: discord.Interaction):
    user = str(interaction.user)
    if not os.path.exists(database_file) or os.path.getsize(database_file) == 0:
        await interaction.response.send_message("❌ You do not have any registered cloud instances.", ephemeral=True)
        return

    embed = discord.Embed(title="Your Cloud Instances", color=EMBED_COLOR)
    found = False

    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 4 and parts[0] == user:
                found = True
                c_id, conn_str, status = parts[1][:12], parts[2], parts[3]
                target_node = parts[4] if len(parts) >= 5 else "node1"
                
                tmate_val = "N/A"
                sshx_val = "N/A"
                if "tmate:" in conn_str:
                    try:
                        tmate_val = conn_str.split("tmate:")[1].split(",sshx:")[0]
                        sshx_val = conn_str.split(",sshx:")[1]
                    except:
                        tmate_val = conn_str

                embed.add_field(
                    name=f"📦 Instance ID: `{c_id}` [{target_node.upper()}]",
                    value=f"**Status:** `{status}`\n**tmate:** `{tmate_val}`\n**sshx:** {sshx_val}",
                    inline=False
                )

    if not found:
        await interaction.response.send_message("❌ You do not have any registered cloud instances.", ephemeral=True)
        return

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="start", description="▶️ Power-on your engine node and rebind tunnel sessions")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def start_cmd(interaction: discord.Interaction, container_id: str):
    user = str(interaction.user)
    target_id, target_node = None, "node1"
    
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id) and parts[0] == user:
                    target_id = parts[1]
                    if len(parts) >= 5: target_node = parts[4]
                    break
                    
    if not target_id:
        await interaction.response.send_message("❌ You do not own a container matching that ID.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        await run_node_command(target_node, f"docker start {target_id}")
        update_database_status(target_id, "Active")
        await interaction.followup.send(f"✅ Your container `{target_id[:12]}` has been powered on.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to start container: {e}", ephemeral=True)

@bot.tree.command(name="stop", description="⏹️ Safely halt running container frameworks and processes")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def stop_cmd(interaction: discord.Interaction, container_id: str):
    user = str(interaction.user)
    target_id, target_node = None, "node1"
    
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id) and parts[0] == user:
                    target_id = parts[1]
                    if len(parts) >= 5: target_node = parts[4]
                    break
                    
    if not target_id:
        await interaction.response.send_message("❌ You do not own a container matching that ID.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        await run_node_command(target_node, f"docker stop {target_id}")
        update_database_status(target_id, "Stopped")
        await interaction.followup.send(f"✅ Your container `{target_id[:12]}` has been safely halted.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to stop container: {e}", ephemeral=True)

@bot.tree.command(name="regen_ssh", description="🔄 Generate fresh remote access routes straight to DMs")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def regen_ssh(interaction: discord.Interaction, container_id: str):
    user = str(interaction.user)
    target_id, target_node = None, "node1"
    
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id) and parts[0] == user:
                    target_id = parts[1]
                    if len(parts) >= 5:
                        target_node = parts[4]
                    break
    
    if not target_id:
        await interaction.response.send_message("❌ You do not own an active container matching that ID.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="🔄 Regenerating Access Routes", description=f"Generating new `tmate` and `sshx` sessions on `{target_node.upper()}`...", color=EMBED_COLOR)
    msg = await interaction.followup.send(embed=embed)
    
    try:
        conn_tmate, tmate_proc = await open_node_process(target_node, f"docker exec {target_id} tmate -F")
        conn_sshx, sshx_proc = await open_node_process(target_node, f"docker exec {target_id} sh -c 'curl -sSf https://sshx.io/get | sh -s run'")

        path_ssh = await capture_ssh_session_line(tmate_proc)
        path_sshx = await capture_sshx_link(sshx_proc)
        
        if path_ssh or path_sshx:
            tmate_display = path_ssh if path_ssh else "Failed to generate tmate session"
            sshx_display = path_sshx if path_sshx else "Failed to generate sshx session"
            
            db_connection_string = f"tmate:{tmate_display},sshx:{sshx_display}"
            update_database_connection(target_id, db_connection_string)
            
            user_embed = discord.Embed(title="✨ Fresh Access Routes Generated!", description=f"Instance: `{target_id[:12]}` on Node: `{target_node.upper()}`", color=EMBED_COLOR)
            user_embed.add_field(name="🔑 tmate SSH Command:", value=f"```{tmate_display}```", inline=False)
            user_embed.add_field(name="🔗 sshx Web Link:", value=f"```{sshx_display}```", inline=False)
            
            try:
                await interaction.user.send(embed=user_embed)
                await msg.edit(embed=discord.Embed(title="✅ Success", description="New access routes have been securely sent to your DMs!", color=0x00FF00))
            except discord.Forbidden:
                await msg.edit(embed=user_embed)
        else:
            await msg.edit(embed=discord.Embed(title="⚠️ Timeout", description="Failed to generate new sessions. Ensure your container is running (`/start`).", color=0xFF0000))
            
        try:
            tmate_proc.terminate()
            sshx_proc.terminate()
            conn_tmate.close()
            conn_sshx.close()
        except: pass
    except Exception as e:
        await msg.edit(embed=discord.Embed(title="❌ Error", description=f"Failed to regenerate links: {e}", color=0xFF0000))

@bot.tree.command(name="rebuild", description="🔄 Factory reset your cloud block to clear data logs")
@app_commands.describe(container_id="The instance ID (first 4+ characters)", os_choice="The new OS image to install")
async def rebuild(interaction: discord.Interaction, container_id: str, os_choice: str):
    user = str(interaction.user)
    target_id = None
    target_node = "node1"
    
    # Locate target container
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id) and parts[0] == user:
                    target_id = parts[1]
                    if len(parts) >= 5:
                        target_node = parts[4]
                    break
                    
    if not target_id:
        await interaction.response.send_message("❌ You do not own a container matching that ID.", ephemeral=True)
        return

    choice = os_choice.lower()
    if choice not in OS_OPTIONS:
        valid_oses = "\n".join([f"{OS_OPTIONS[os_id]['emoji']} **{os_id}**" for os_id in OS_OPTIONS.keys()])
        await interaction.response.send_message(f"❌ Invalid OS selection. Available options:\n{valid_oses}", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    embed = discord.Embed(title="🔄 Factory Reset Initiated", description=f"Destroying instance `{target_id[:12]}` and wiping data blocks on `{target_node.upper()}`...", color=0xFFA500)
    msg = await interaction.followup.send(embed=embed)
    
    try:
        # Destroy the old container
        await run_node_command(target_node, f"docker rm -f {target_id}")
        remove_from_database_by_id(target_id)
        
        os_data = OS_OPTIONS[choice]
        embed.description = f"Spinning up fresh {os_data['name']} environment..."
        await msg.edit(embed=embed)
        
        # Provision a new one
        exit_code, stdout, stderr = await run_node_command(target_node, f"docker run -itd --privileged --memory={RAM_LIMIT} --name=vps-{interaction.user.id}-{int(time.time())} {os_data['image']}")
        if exit_code != 0: 
            raise Exception(stderr.strip())
            
        new_container_id = stdout.strip()
        await asyncio.sleep(4)
        
        # Open parallel interactive tunnels
        conn_tmate, tmate_proc = await open_node_process(target_node, f"docker exec {new_container_id} tmate -F")
        conn_sshx, sshx_proc = await open_node_process(target_node, f"docker exec {new_container_id} sh -c 'curl -sSf https://sshx.io/get | sh -s run'")

        path_ssh = await capture_ssh_session_line(tmate_proc)
        path_sshx = await capture_sshx_link(sshx_proc)
        
        tmate_display = path_ssh if path_ssh else "Failed"
        sshx_display = path_sshx if path_sshx else "Failed"
        
        db_connection_string = f"tmate:{tmate_display},sshx:{sshx_display}"
        # Persist to local cluster DB safely using the string reference representation
        add_to_database(user, new_container_id, db_connection_string, "Active", target_node)
        
        success_embed = discord.Embed(title="✅ Rebuild Complete", description=f"Your instance has been factory reset. New ID: `{new_container_id[:12]}`", color=0x00FF00)
        success_embed.add_field(name="🔑 New tmate SSH:", value=f"```{tmate_display}```", inline=False)
        success_embed.add_field(name="🔗 New sshx Link:", value=f"```{sshx_display}```", inline=False)
        
        try:
            await interaction.user.send(embed=success_embed)
            await msg.edit(embed=discord.Embed(title="✅ Rebuild Complete", description=f"Instance `{new_container_id[:12]}` rebuilt successfully. Check your DMs for new credentials!", color=0x00FF00))
        except discord.Forbidden:
            await msg.edit(embed=success_embed)
            
        try:
            tmate_proc.terminate()
            sshx_proc.terminate()
            conn_tmate.close()
            conn_sshx.close()
        except: 
            pass
        
    except Exception as e:
        await msg.edit(embed=discord.Embed(title="❌ Rebuild Failed", description=f"```\n{e}\n```", color=0xFF0000))

# ==================== ADMINISTRATIVE COMMANDS ====================

@bot.tree.command(name="admin_list", description="👑 [ADMIN] Scan all configured physical nodes and list total active container IDs")
async def admin_list_cmd(interaction: discord.Interaction):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    
    embed = discord.Embed(
        title="🕵️ Cluster Inspection Engine",
        description="Connecting to all cloud nodes to query real-time container states...",
        color=EMBED_COLOR
    )
    msg = await interaction.followup.send(embed=embed)
    
    db_owners = get_database_mapping()
    total_running_containers = 0
    node_reports = []

    for node_key in sorted(NODES.keys()):
        try:
            exit_code, stdout, stderr = await run_node_command(
                node_key, 
                "docker ps --format '{{.ID}}|{{.Names}}'"
            )
            
            if exit_code == 0:
                lines = [line.strip() for line in stdout.strip().split('\n') if line.strip()]
                node_container_count = len(lines)
                total_running_containers += node_container_count
                
                container_details = []
                for idx, line in enumerate(lines, 1):
                    parts = line.split('|')
                    c_id = parts[0][:12] if parts[0] else "UnknownID"
                    c_name = parts[1] if len(parts) > 1 else "unnamed"
                    
                    owner_match = "System/Unknown"
                    for stored_id, owner_user in db_owners.items():
                        if stored_id.startswith(parts[0]) or parts[0].startswith(stored_id):
                            owner_match = owner_user
                            break
                            
                    container_details.append(f"{idx}. ID: `{c_id}` | Name: `{c_name}`\n   Owner: `{owner_match}`")
                
                details_text = "\n".join(container_details) if container_details else "*No active containers running.*"
                node_reports.append((f"🌐 {node_key.upper()} ({node_container_count} Active)", details_text))
            else:
                node_reports.append((f"🔴 {node_key.upper()} (Error)", f"```\nFailed to run docker ps: {stderr[:100]}\n```"))
        except Exception as err:
            node_reports.append((f"🔴 {node_key.upper()} (Unreachable)", f"```\nConnection lost: {str(err)[:100]}\n```"))

    final_embed = discord.Embed(
        title="📋 Cluster-Wide Global Node Manifest",
        description=f"**Total Tracked Container Instances:** `{total_running_containers}` running environments.",
        color=0x00FF00,
        timestamp=datetime.utcnow()
    )
    
    for title, value in node_reports:
        if len(value) > 1024:
            value = value[:1000] + "\n...[Truncated due to field length limits]"
        final_embed.add_field(name=title, value=value, inline=False)
        
    await msg.edit(embed=final_embed)

@bot.tree.command(name="admin_add", description="👑 [ADMIN] Register a user to the script admin database file | Made by DevaByss")
@app_commands.describe(user="The user to grant script permissions")
async def admin_add(interaction: discord.Interaction, user: discord.Member):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    admins = []
    if os.path.exists(admin_file):
        with open(admin_file, 'r') as f:
            admins = [line.strip() for line in f.readlines()]

    if str(user.id) in admins:
        await interaction.response.send_message(f"ℹ️ {user.mention} is already an administrator.", ephemeral=True)
        return

    with open(admin_file, 'a') as f:
        f.write(f"{user.id}\n")

    await interaction.response.send_message(f"✅ Successfully promoted {user.mention} to script administrator.", ephemeral=True)

@bot.tree.command(name="admin_remove", description="👑 [ADMIN] Revoke a user's rights from the script admin database file | Made by DevaByss")
@app_commands.describe(user="The user to revoke script permissions from")
async def admin_remove(interaction: discord.Interaction, user: discord.Member):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    if not os.path.exists(admin_file):
        await interaction.response.send_message("ℹ️ No users found inside the administrator registry database.", ephemeral=True)
        return

    with open(admin_file, 'r') as f:
        admins = [line.strip() for line in f.readlines()]

    if str(user.id) not in admins:
        await interaction.response.send_message(f"❌ {user.mention} is not an administrator.", ephemeral=True)
        return

    admins.remove(str(user.id))
    with open(admin_file, 'w') as f:
        for admin in admins:
            f.write(f"{admin}\n")

    await interaction.response.send_message(f"✅ Successfully demoted {user.mention} from script administrator rights.", ephemeral=True)

@bot.tree.command(name="vps_suspend", description="🔒 [ADMIN] Suspend a user's cloud instance network access | Made by DevaByss")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def vps_suspend(interaction: discord.Interaction, container_id: str):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    target_id, target_user, target_node = None, None, "node1"
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id):
                    target_user, target_id = parts[0], parts[1]
                    if len(parts) >= 5: target_node = parts[4]
                    break

    if not target_id:
        await interaction.response.send_message("❌ No target instance found matching that ID prefix.", ephemeral=True)
        return

    embed = discord.Embed(title=f"🔒 Suspending Instance {target_id[:12]} on {target_node.upper()}", description="Disconnecting container network bridge infrastructure...", color=0xFFA500)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    try:
        await run_node_command(target_node, f"docker network disconnect bridge {target_id}")
        await run_node_command(target_node, f"docker stop {target_id}")
        update_database_status(target_id, "Suspended")
        embed = discord.Embed(title="🔒 Instance Suspended", description=f"Instance `{target_id[:12]}` (Node: `{target_node}`, Owned by: `{target_user}`) has been locked down network-side.", color=0xFF0000)
        await msg.edit(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Suspension Failed", description=f"```\n{e}\n```", color=0xFF0000)
        await msg.edit(embed=embed)

@bot.tree.command(name="deploy", description="🚀 [ADMIN] Deploy a customized VPS architecture image node for a client")
@app_commands.describe(user="The target owner", os_choice="OS profile choice", node_choice="Target node cluster placement")
@app_commands.choices(node_choice=[
    app_commands.Choice(name="Node 1", value="node1"),
    app_commands.Choice(name="Node 2", value="node2"),
    app_commands.Choice(name="Node 3", value="node3"),
    app_commands.Choice(name="Node 4", value="node4"),
    app_commands.Choice(name="Node 5", value="node5")
])
async def deploy_cmd(interaction: discord.Interaction, user: discord.User, os_choice: str, node_choice: str = "node1"):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    choice = os_choice.lower()
    if choice not in OS_OPTIONS:
        await interaction.response.send_message("❌ Invalid OS selection profile.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    os_data = OS_OPTIONS[choice]
    embed = discord.Embed(title="🚀 Initializing Architecture Deployment", description=f"Provisioning {os_data['name']} on {node_choice.upper()}...", color=EMBED_COLOR)
    msg = await interaction.followup.send(embed=embed)

    try:
        cmd = f"docker run -itd --privileged --memory={RAM_LIMIT} --name=vps-{user.id}-{int(time.time())} {os_data['image']}"
        exit_code, stdout, stderr = await run_node_command(node_choice, cmd)
        if exit_code != 0: raise Exception(stderr.strip())

        container_id = stdout.strip()
        await asyncio.sleep(4)

        conn_tmate, tmate_proc = await open_node_process(node_choice, f"docker exec {container_id} tmate -F")
        conn_sshx, sshx_proc = await open_node_process(node_choice, f"docker exec {container_id} sh -c 'curl -sSf https://sshx.io/get | sh -s run'")

        path_ssh = await capture_ssh_session_line(tmate_proc)
        path_sshx = await capture_sshx_link(sshx_proc)

        tmate_display = path_ssh if path_ssh else "Failed Setup"
        sshx_display = path_sshx if path_sshx else "Failed Setup"

        db_connection_string = f"tmate:{tmate_display},sshx:{sshx_display}"
        add_to_database(str(user), container_id, db_connection_string, "Active", node_choice)

        success_embed = discord.Embed(title="✅ Node Cluster Deployment Completed", color=0x00FF00)
        success_embed.add_field(name="📦 Allocated Container ID", value=f"`{container_id[:12]}`", inline=True)
        success_embed.add_field(name="👑 Assigner/Owner Flag", value=user.mention, inline=True)
        success_embed.add_field(name="🔑 Terminal Route SSH String", value=f"```{tmate_display}```", inline=False)
        success_embed.add_field(name="🔗 Web Control Panel Link", value=f"```{sshx_display}```", inline=False)

        try:
            target_dm_user = await bot.fetch_user(user.id)
            await target_dm_user.send(embed=success_embed)
            
            public_embed = discord.Embed(
                title="📬 Deployment Completed Successfully",
                description=f"Architecture node successfully created on `{node_choice.upper()}`! The connection details and access routes have been delivered straight to {user.mention}'s DMs.",
                color=0x00FF00
            )
            public_embed.add_field(name="📦 Container ID", value=f"`{container_id[:12]}`", inline=True)
            public_embed.add_field(name="🐧 OS Installed", value=f"`{os_data['name']}`", inline=True)
            await msg.edit(content=None, embed=public_embed)
            
        except discord.Forbidden:
            fail_embed = discord.Embed(
                title="⚠️ DM Delivery Failed",
                description=f"The instance was successfully provisioned, but {user.mention} has their privacy options configured to deny Direct Messages. Open DMs and type `/regen_ssh` to recover details.",
                color=0xFFA500
            )
            await msg.edit(content=None, embed=fail_embed)
        except Exception as dm_err:
            await msg.edit(content=f"⚠️ **DM Routing Engine Failure:** `{dm_err}`", embed=None)

        try:
            tmate_proc.terminate()
            sshx_proc.terminate()
            conn_tmate.close()
            conn_sshx.close()
        except: pass

    except Exception as e:
        await msg.edit(embed=discord.Embed(title="❌ Deployment Engine Fatal Error", description=f"```\n{e}\n```", color=0xFF0000))

@bot.tree.command(name="vps_unsuspend", description="🔓 [ADMIN] Restore core network bridge pathways for a suspended container")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def vps_unsuspend(interaction: discord.Interaction, container_id: str):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    target_id, target_user, target_node = None, None, "node1"
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id):
                    target_user, target_id = parts[0], parts[1]
                    if len(parts) >= 5: target_node = parts[4]
                    break

    if not target_id:
        await interaction.response.send_message("❌ No target instance found matching that ID prefix.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    try:
        await run_node_command(target_node, f"docker network connect bridge {target_id}")
        await run_node_command(target_node, f"docker start {target_id}")
        update_database_status(target_id, "Active")
        await interaction.followup.send(f"🔓 Network access restored for `{target_id[:12]}` on `{target_node.upper()}`.")
    except Exception as e:
        await interaction.followup.send(f"❌ Re-connection failure: ```\n{e}\n```")

@bot.tree.command(name="vps_delete", description="🗑️ [ADMIN] Permanently destroy and wipe a user container completely")
@app_commands.describe(container_id="The instance ID (first 4+ characters)")
async def vps_delete(interaction: discord.Interaction, container_id: str):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ This command is restricted to administrators.", ephemeral=True)
        return

    target_id, target_node = None, "node1"
    if os.path.exists(database_file):
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[1].startswith(container_id):
                    target_id = parts[1]
                    if len(parts) >= 5: target_node = parts[4]
                    break

    if not target_id:
        await interaction.response.send_message("❌ No target instance found matching that ID prefix.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    try:
        await run_node_command(target_node, f"docker rm -f {target_id}")
        remove_from_database_by_id(target_id)
        await interaction.followup.send(f"🗑️ Container `{target_id[:12]}` has been permanently purged from `{target_node.upper()}` and database logs dropped.")
    except Exception as e:
        await interaction.followup.send(f"❌ Deletion failure: ```\n{e}\n```")

# Run bot configuration loop
if __name__ == "__main__":
    if TOKEN == 'YOUR_FALLBACK_TOKEN_HERE':
        print("❌ Please configure DISCORD_BOT_TOKEN before running the framework.")
    else:
        bot.run(TOKEN)