import csv, random
random.seed(42)
rows = []
for _ in range(300):
    f1 = round(random.gauss(0, 1), 4)
    f2 = round(random.gauss(0, 1), 4)
    f3 = round(random.uniform(0, 10), 4)
    target = 1 if (f1 + f2 + 0.5 * f3) > 0 else 0
    rows.append([f1, f2, f3, target])

with open("/home/claude/compose_generator/ml_pipeline/data/dataset.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["feature_1", "feature_2", "feature_3", "target"])
    writer.writerows(rows)
print("dataset.csv written")
