def sum(a, b):
    total = a + b
    
    if total > 10:
        return total * 3
    else:
        return total


result1 = sum(3, 4)
print(f"The sum of 3 and 4 is: {result1}")