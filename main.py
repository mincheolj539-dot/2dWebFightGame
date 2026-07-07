"""진입점 (Entry point).

로컬 실행:  python main.py
웹 빌드:    pygbag .   (그 후 브라우저에서 http://localhost:8000)

Pygbag(브라우저) 호환을 위해 반드시 async main + asyncio.run 구조를 유지한다.
"""

import asyncio

import pygame

from game.game import Game


async def main():
    pygame.init()
    try:
        game = Game()
        await game.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
