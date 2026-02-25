def linesInFile(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return sum(1 for _ in file)
    
def getAccounts(filePath, amount):
    if linesInFile(filePath) < amount:
        return []

    with open(filePath, 'r') as file:
        all_lines = file.readlines()

    result = all_lines[:amount]
    remaining = all_lines[amount:]
    with open(filePath, 'w') as file:
        file.writelines(remaining)

    return result