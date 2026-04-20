class SignType:

    SYMBOL = {
        True: "signed",
        False: ""
    }

    @property
    def val(self) -> bool:
        return self._val
    
    @property
    def symbol(self) -> str:
        return self._symbol

    def __init__(self, signed: bool):
        self._val = signed
        self._symbol = self.SYMBOL[signed]
