import asyncio
import re

import aiohttp

ENV = '/opt/imobiliare/bot/.env'


def token() -> str:
    """Read BOT_TOKEN from the server .env - never hardcode it."""
    return re.search(r'^BOT_TOKEN=(\S+)', open(ENV).read(), re.M).group(1)


async def main():
    url = f'https://api.telegram.org/bot{token()}/setMyProfilePhoto'
    async with aiohttp.ClientSession() as sess:
        with open('/root/avatar2.png', 'rb') as f:
            data = f.read()
        form = aiohttp.FormData()
        form.add_field('photo', data, filename='avatar2.png', content_type='image/png')
        async with sess.post(url, data=form) as resp:
            print(await resp.text())

asyncio.run(main())
