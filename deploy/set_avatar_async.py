import asyncio
import aiohttp

async def main():
    token = 'REPLACE_WITH_BOT_TOKEN_FROM_ENV'
    url = f'https://api.telegram.org/bot{token}/setMyProfilePhoto'
    async with aiohttp.ClientSession() as sess:
        with open('/root/avatar2.png', 'rb') as f:
            data = f.read()
        form = aiohttp.FormData()
        form.add_field('photo', data, filename='avatar2.png', content_type='image/png')
        async with sess.post(url, data=form) as resp:
            print(await resp.text())

asyncio.run(main())
