import yaml

cookie_str = """enter_pc_once=1; UIFID_TEMP=8f584679f13361d7674396b25a46f1c75dd7736730eef2bca7f1b3cfea8b216d569b433c01ea69132b346162888ade2fd392ba388916c6a28be467332d82e12bc85389a39429ad1c5956933d26f2309d; hevc_supported=true; passport_csrf_token=ed778bed4731372d341b5db49069a6e4; passport_csrf_token_default=ed778bed4731372d341b5db49069a6e4; UIFID=8f584679f13361d7674396b25a46f1c75dd7736730eef2bca7f1b3cfea8b216dbb4826b0a36b6285c224ac77a2c7e3c96570d36aec1d514f5abbfb9bb3249f1a95264cc8fd627b91e860591d1e163ac6ff96ce769e9f127f078489e7a6fcfeb79e8be18d7cc4e35a76983f48e782219cadce3243e9e1429db6027b0801392000c0721fea5738e3780342e41bc87b3866a40cbd8ae1cc78b45a4518763a4e6cef; bd_ticket_guard_client_web_domain=2; passport_assist_user=CkRrGOQTddDP1F6yIxu4A2nSbu69Pexv0mzXOkMUiqbs_Ev07OuQhQGaAWerrO7UDdOJNEf6UUzofPBDgPZsim38q63LnBpKCjwAAAAAAAAAAAAAUF-DaxLq6Npms-e4Wh17VWnIVWnNV1KG0zWXXhOliRg_tWqIqLJiEboVo_c3aBhXkMAQo66QDhiJr9ZUIAEiAQO0IhjF; n_mh=1eMa9fT5fwdeUWJJg4ZJzBmtZS96_V4nDOA1XMH7c6w; uid_tt=6c42ef862d2da00acd4740a1302a195ffac755a7fc023d3656c82cdde7209342; uid_tt_ss=6c42ef862d2da00acd4740a1302a195ffac755a7fc023d3656c82cdde7209342; sid_tt=a85817b802a6cfee0909a53779e33b95; sessionid=a85817b802a6cfee0909a53779e33b95; sessionid_ss=a85817b802a6cfee0909a53779e33b95; is_staff_user=false; has_biz_token=false; _bd_ticket_crypt_cookie=b3c447b021c94940281eb56f4be0d8c0; __security_mc_1_s_sdk_sign_data_key_web_protect=d35ea467-4151-a981; __security_mc_1_s_sdk_cert_key=6d4a6934-40b4-b977; __security_mc_1_s_sdk_crypt_sdk=a4218d61-4e00-afd0; __security_server_data_status=1; login_time=1777710658072; SelfTabRedDotControl=%5B%5D; is_support_rtm_web_ts=1; publish_badge_show_info=%222%2F20260622%2F0%22; FOLLOW_NUMBER_YELLOW_POINT_INFO=%22MS4wLjABAAAAIoPomZtGOEKAVd55u0sabraeR2VmzSA-f51ol53cQZEddZLzUatYf5IjgOfV_05o%2F1782144000000%2F0%2F1782130216354%2F0%22; strategyABtestKey=%221782130216.437%22; ttwid=1%7CrP9oucVtvvz1559JEMcQICsuYb8mBj0Yu7dVWgAGhZc%7C1782130216%7C8ac274b1b5fbcc84b4d03f91b5df10e07ac692cefc4aa201a8cd8173b1f69a7a; sid_guard=a85817b802a6cfee0909a53779e33b95%7C1782130222%7C5184000%7CFri%2C+21-Aug-2026+12%3A10%3A22+GMT; session_tlb_tag=sttt%7C11%7CqFgXuAKmz-4JCaU3eeM7lf_________0tIt8OkzYKMUTZwjQVLl4LWP0Hbz9y5UQ7Akc7_kxWA0%3D; sid_ucp_v1=1.0.0-KGY4YmU1ZGYyNDMzODNlZGVjNDEyZjlkOTZlMmY0Y2QxM2JkMDhmNjkKIgi6iIDwibLJ6mgQrszk0QYY7zEgDDC9ztTGBjgHQPQHSAQaAmxmIiBhODU4MTdiODAyYTZjZmVlMDkwOWE1Mzc3OWUzM2I5NQ; ssid_ucp_v1=1.0.0-KGY4YmU1ZGYyNDMzODNlZGVjNDEyZjlkOTZlMmY0Y2QxM2JkMDhmNjkKIgi6iIDwibLJ6mgQrszk0QYY7zEgDDC9ztTGBjgHQPQHSAQaAmxmIiBhODU4MTdiODAyYTZjZmVlMDkwOWE1Mzc3OWUzM2I5NQ; is_dash_user=1; download_guide=%222%2F20260622%2F0%22; sdk_source_info=7e276470716a68645a606960273f276364697660272927676c715a6d6069756077273f276364697660272927666d776a68605a607d71606b766c6a6b5a7666776c7571273f275e58272927666a6b766a69605a696c6061273f27636469766027292762696a6764695a7364776c6467696076273f275e582729277672715a646971273f2763646976602729277f6b5a666475273f2763646976602729276d6a6e5a6b6a716c273f2763646976602729276c6b6f5a7f6367273f27636469766027292771273f27353330303535363634373d3234272927676c715a75776a716a666a69273f2763646976602778; bit_env=Eg2wCegT-SZx-7VIKRwCMAWia6YTaWr35j-9HdXWFj2qlO9NOPr0m3_9vliLLSxAD8140t8b95bObACISjWmz44qbe3z18PRpxndrqUu1qebO6vBmHMw8IK5wVk4XnEcZD6hXcpLQnoFZFTGNN8dgLYwHqyvo1uKy9-J-K8580CvkqjD2t6VlkRoI3N_9mUyesi3SngR8Lc5e_XazSg2XCI2R_EWGV1-49S08Qi6M98gYOEi9Tg5nxiBKl-NlQjjKJtenfE-yhT0mkQV9hzKLzo4NzA6Sxo6gUI74bvSxZRZ46gy_iGetIJWDbWgBCoDsqwbptDC89UR1WaXHFR3_Ya7vCNE8W_ArCftgvHEB-RvT3k-Lz7xltXvCXroq2NUk3WcUUB90hjhaDvMhnTNqVmddVA_SypFXD3SywAFXYgb-xz4bfJShUUUMZbBGFsE8u0KNil3Xy0elp6kaGxWFlEn6_tUK5B46yP3zUZ5CKd5lmb6__B4cQSwlbb0sX-VwnsFpTidhtQd9WaQ0-u_oPYh-Ussoq-O_CFIgNC09gE%3D; gulu_source_res=eyJwX2luIjoiYTFjNWIwODAxN2UyMjMzYmIwMTI4OGM3ZDdiZTc3ZDA1MmNlN2Q1NDk2MTY0NmM2M2Q3MjQzMDBjNzcwZjRjMSJ9; passport_auth_mix_state=jvlnw1150t30372eb3fejds534dz2qqe467pjndd85pmzsbw; IsDouyinActive=true; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A3440%2C%5C%22screen_height%5C%22%3A1440%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A20%2C%5C%22device_memory%5C%22%3A32%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A50%7D%22; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCSjJsOVk1WndyWTNIREwyUGkyS00vZmtCN2Z4N09GUjBiRzN5MktqbDJQb2MzS1c4SmEzVlY4bC8xa0MvTHMrUnNBbTBnWnl5cGlVTG5MN2RlaDlOUk09IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D; home_can_add_dy_2_desktop=%221%22; biz_trace_id=00fec632; odin_tt=73cf7cbd2665957ea494b643d1308636e0a4e506e954fd1839b060370cdb3336d312b5dd5ef18a2d3ae6232053de9af43db53a75246de3b3ee400f746d6893e3; bd_ticket_guard_client_data_v2=eyJyZWVfcHVibGljX2tleSI6IkJKMmw5WTVad3JZM0hETDJQaTJLTS9ma0I3Zng3T0ZSMGJHM3kyS2psMlBvYzNLVzhKYTNWVjhsLzFrQy9McytSc0FtMGdaeXlwaVVMbkw3ZGVoOU5STT0iLCJ0c19zaWduIjoidHMuMi5jOTBiMDNhOWMzYzhhYjM4YWJjNDhhYWFkNDliY2RmOGVmZmRkNmQ5Njc2NDcyZDA5YjE1YTMxNDU2ZTE4MzM2YzRmYmU4N2QyMzE5Y2YwNTMxODYyNGNlZGExNDkxMWNhNDA2ZGVkYmViZWRkYjJlMzBmY2U4ZDRmYTAyNTc1ZCIsInJlcV9jb250ZW50Ijoic2VjX3RzIiwicmVxX3NpZ24iOiJlNFFMN2pUb1UvcWhnTGhCUDJKVk9BYVhhb3owYTVQcGE4Z0NqSmVWeU9FPSIsInNlY190cyI6IiNoRUNyRFBmTWtXbVZGQUdqNmU3ejFsTWMwWHlTM25ucmFaQzllUlZoR1BXQ1BsZ2VwT0VGZ2tVZnFJeTIifQ%3D%3D"""

parsed = {}
for part in cookie_str.split('; '):
    if '=' in part:
        k, v = part.split('=', 1)
        parsed[k.strip()] = v.strip()

with open('config.yml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

key_map = {
    'msToken': 'msToken',
    'ttwid': 'ttwid',
    'odin_tt': 'odin_tt',
    'passport_csrf_token': 'passport_csrf_token',
    'sid_guard': 'sid_guard',
    'sessionid': 'sessionid',
    'sid_tt': 'sid_tt',
}

for cfg_key, cookie_key in key_map.items():
    if cookie_key in parsed:
        config['cookies'][cfg_key] = parsed[cookie_key]
        print(f"Updated {cfg_key}")
    else:
        print(f"Kept existing {cfg_key}")

for k in ['UIFID', 'UIFID_TEMP', '__ac_nonce', '__ac_signature', 's_v_web_id', 'x-web-secsdk-uid']:
    if k in parsed:
        config['cookies'][k] = parsed[k]

config['number']['post'] = 1

with open('config.yml', 'w', encoding='utf-8') as f:
    yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

print("配置已更新，将下载该用户全部视频")
