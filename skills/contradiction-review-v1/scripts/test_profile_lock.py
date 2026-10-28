import tempfile,unittest
from pathlib import Path
from profile_lock import acquire_profile_lock
class ProfileExclusion(unittest.TestCase):
    def test_two_open_handles_cannot_share_profile_and_close_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'profile.lock';path.write_text('0',encoding='utf-8')
            with path.open('r+',encoding='utf-8') as first:
                acquire_profile_lock(first)
                with path.open('r+',encoding='utf-8') as second:
                    with self.assertRaises(BlockingIOError):acquire_profile_lock(second)
            with path.open('r+',encoding='utf-8') as third:acquire_profile_lock(third)
if __name__=='__main__':unittest.main()
