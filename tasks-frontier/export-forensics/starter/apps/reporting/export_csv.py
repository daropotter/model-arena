# Legacy UI exporter. Last deployed in 2024.
def export(rows):
    return ','.join(rows).encode('latin1')

if __name__ == '__main__':print(export(['id','amount']))
