from collections import Counter

with open("years.txt", "r") as f:
    words = f.read().splitlines()

print(Counter(words))