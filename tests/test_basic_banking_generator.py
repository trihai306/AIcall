import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('basic_generator', Path(__file__).resolve().parents[1] / 'scripts/generate_basic_banking_qwen9b.py')
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)

class GeneratorValidationTests(unittest.TestCase):
    def test_accepts_generic_answer(self):
        self.assertEqual(generator.rejection('Thẻ ghi nợ dùng để làm gì?', 'Thẻ ghi nợ giúp thanh toán hoặc rút tiền từ tài khoản gắn với thẻ.'), '')

    def test_rejects_numeric_policy(self):
        self.assertEqual(generator.rejection('Chuyển khoản xử lý thế nào?', 'Giao dịch của bạn chắc chắn hoàn tất sau 24 giờ.'), 'numbers_or_links')

    def test_rejects_documents(self):
        self.assertEqual(generator.rejection('Muốn đăng ký cần làm gì?', 'Bạn cần chuẩn bị hồ sơ và giấy tờ để đăng ký dịch vụ.'), 'excluded_scope')

    def test_rejects_secret_request_but_allows_warning(self):
        question = 'Tôi có nên chia sẻ mã xác thực không?'
        self.assertEqual(generator.rejection(question, 'Bạn hãy cung cấp mã OTP cho nhân viên để tiếp tục.'), 'secret_request')
        self.assertEqual(generator.rejection(question, 'Không cung cấp mã OTP cho người khác; chỉ dùng mã trên kênh chính thức.'), '')

    def test_rejects_fabricated_action(self):
        self.assertEqual(generator.rejection('Thẻ của tôi đang bị mất?', 'Em đã khóa thẻ của anh và xử lý xong yêu cầu này.'), 'fabricated_action')

    def test_negation_does_not_hide_later_request(self):
        self.assertEqual(generator.rejection('Tôi nên xử lý mã xác thực thế nào?', 'Không chia sẻ mã OTP với người lạ. Bạn hãy gửi mã OTP cho em.'), 'secret_request')

    def test_rejects_spelled_out_timing(self):
        self.assertEqual(generator.rejection('Tôi nhận lại tiền khi nào?', 'Bạn sẽ nhận lại tiền sau hai ngày kể từ khi thông báo.'), 'quantified_or_promised')

    def test_unknown_gpu_state_is_not_permission(self):
        with patch.object(generator, 'get_json', return_value={}):
            with self.assertRaises(generator.GPUBusy):
                generator.check_gpu('http://local-test')

    def test_duplicate_normalization(self):
        self.assertEqual(generator.normalize('Thẻ ghi nợ là gì?'), generator.normalize('  THE GHI NO LA GI  '))

    def test_busy_guard_fails_closed(self):
        with patch.object(generator, 'get_json', return_value={'can_use_gpu': False, 'reason': 'customer service'}):
            with self.assertRaises(generator.GPUBusy):
                generator.check_gpu('http://local-test')

if __name__ == '__main__':
    unittest.main()
