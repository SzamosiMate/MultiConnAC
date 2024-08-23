class Port(int):
    def __new__(cls, value):
        if not (19723 <= value <= 19744):
            raise ValueError(f"Port value must be between 19723 and 19744, got {value}.")
        return int.__new__(cls, value)

# Example usage:
port = Port(19725)  # This will succeed
print(type(port + 2))


