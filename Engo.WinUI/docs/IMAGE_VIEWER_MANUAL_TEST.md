# Image viewer — manual Windows checks

These checks complement the automated viewport-math smoke tests. They require launching the unpackaged WinUI app on Windows.

1. Open a large PNG or JPEG. Confirm it initially fits inside the image surface and the zoom percentage reflects the applied fit scale.
2. Put the pointer over a recognizable detail and rotate the mouse wheel up. Confirm the detail stays underneath the pointer while the image grows.
3. Rotate the wheel down. Confirm the image shrinks around the pointer rather than jumping toward the top-left corner.
4. Zoom beyond 100%, then hold the left mouse button and drag right, left, up, and down. Confirm the visible image follows the pointer in each direction and the scroll offsets never move beyond the image edges.
5. Use the toolbar's **تصغير**, **100%**, **ملاءمة**, and **تكبير** buttons. Confirm the zoom label updates.
6. Resize the window while **ملاءمة** is active. Confirm the image continues to fit. Then manually zoom and resize again; confirm the chosen manual zoom is not unexpectedly reset.
7. Repeat with TIFF, BMP, GIF, and WebP files available on the test machine. Record any codec-specific file that Windows cannot decode.

The source-level smoke tests verify the pointer-anchored zoom formula, drag direction, and non-negative scroll-offset clamping. They do not simulate WinUI pointer routing or replace these manual checks.
