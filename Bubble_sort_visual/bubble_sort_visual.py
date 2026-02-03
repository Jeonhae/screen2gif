#!/usr/bin/env python3
import argparse
import random
import matplotlib.pyplot as plt
import matplotlib.animation as animation


def bubble_sort_gen(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            yield ("compare", j, j + 1, arr.copy())
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                yield ("swap", j, j + 1, arr.copy())
    yield ("done", None, None, arr.copy())


def visualize(arr, interval=200):
    fig, ax = plt.subplots()
    ax.set_title("Bubble Sort Visualization")
    bar_rects = ax.bar(range(len(arr)), arr, align="edge")
    ax.set_xlim(0, len(arr))
    ax.set_ylim(0, max(arr) * 1.1 if arr else 1)

    text = ax.text(0.02, 0.95, "", transform=ax.transAxes)
    generator = bubble_sort_gen(arr.copy())

    def update(frame):
        try:
            typ, i, j, state = next(generator)
        except StopIteration:
            return bar_rects
        for rect, val in zip(bar_rects, state):
            rect.set_height(val)
        for rect in bar_rects:
            rect.set_color('#1f77b4')
        if typ == 'compare':
            bar_rects[i].set_color('red')
            bar_rects[j].set_color('red')
            text.set_text(f"Comparing: {state[i]} and {state[j]}")
        elif typ == 'swap':
            bar_rects[i].set_color('green')
            bar_rects[j].set_color('green')
            text.set_text(f"Swapped: {state[i]} and {state[j]}")
        elif typ == 'done':
            for rect in bar_rects:
                rect.set_color('green')
            text.set_text("Sorted")
            ani.event_source.stop()
        return bar_rects

    ani = animation.FuncAnimation(fig, update, frames=range(100000), interval=interval, repeat=False, blit=False)
    plt.show()


def parse_args():
    parser = argparse.ArgumentParser(description="Bubble Sort Visualization")
    parser.add_argument('--size', type=int, default=20, help='Number of elements')
    parser.add_argument('--interval', type=int, default=200, help='Animation interval in ms')
    parser.add_argument('--seed', type=int, help='Random seed')
    parser.add_argument('--list', nargs='+', type=int, help='Provide list of integers to sort')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.list:
        arr = args.list
    else:
        if args.seed is not None:
            random.seed(args.seed)
        arr = random.sample(range(1, args.size * 5 + 1), args.size)
    visualize(arr, interval=args.interval)


if __name__ == '__main__':
    main()
