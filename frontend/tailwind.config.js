// Config Tailwind cho bản build tĩnh (offline).
// Trước đây config này nằm inline trong index.html và chạy bằng cdn.tailwindcss.com
// -> phải có internet mới có CSS. Tách ra đây để build sẵn 1 file .css.
//
// Build lại sau khi sửa giao diện:
//   npx tailwindcss@3 -c frontend/tailwind.config.js -i frontend/tailwind.input.css -o frontend/tailwind.css --minify
module.exports = {
  content: [
    './frontend/index.html',
    './frontend/app.js',
    // Các trang bổ sung theo Điều 6 hợp đồng. Quên file này thì class chỉ dùng
    // trong đó bị loại khỏi bản build và giao diện vỡ ĐÚNG ở những trang mới.
    './frontend/trang_moi.js',
  ],
  theme: {
    extend: {
      colors: {
        void: '#06080f',
        abyss: '#0b0f1a',
        deep: '#111827',
        slate: { 750: '#1e293b', 650: '#2d3a4f' },
        cyan: { 400: '#22d3ee', 500: '#06b6d4' },
        emerald: { 400: '#34d399', 500: '#10b981' },
      },
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'fade-up': 'fadeUp 0.3s ease-out',
        'pulse-ring': 'pulseRing 2s ease-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'slide-in': 'slideIn 0.2s ease-out',
      },
      keyframes: {
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        pulseRing: { '0%': { boxShadow: '0 0 0 0 rgba(6,182,212,0.4)' }, '70%': { boxShadow: '0 0 0 14px rgba(6,182,212,0)' }, '100%': { boxShadow: '0 0 0 0 rgba(6,182,212,0)' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        slideIn: { '0%': { opacity: '0', transform: 'translateX(-8px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
      },
    },
  },
};
