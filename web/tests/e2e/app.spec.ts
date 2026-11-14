import { test, expect } from '@playwright/test';
import { blankProject, updatePhotos } from '../../src/model';

test('opening a Drive link requests consent before reading any files', async ({ page }) => {
  const requests: { authorization: string | undefined }[] = [];
  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `window.google = {accounts: {oauth2: {
      initTokenClient(options) {return {requestAccessToken() {
        window.grantTestDriveConsent = () => options.callback({access_token: 'test-drive-token', expires_in: 3600, scope: 'https://www.googleapis.com/auth/drive.readonly'});
      }};}, hasGrantedAllScopes() {return true;}
    }}};`,
    }),
  );
  await page.route('https://www.googleapis.com/drive/v3/**', async (route) => {
    requests.push({ authorization: route.request().headers().authorization });
    const url = new URL(route.request().url());
    await route.fulfill({
      json: url.pathname.endsWith('/files/folder123')
        ? { id: 'folder123', name: 'Drive test', mimeType: 'application/vnd.google-apps.folder' }
        : { files: [{ id: 'photo123', name: 'test.jpg', mimeType: 'image/jpeg' }] },
    });
  });
  await page.goto('/');
  await page.waitForFunction(() => Boolean((window as unknown as { google?: unknown }).google));
  await page.getByRole('button', { name: 'Mở link Google Drive', exact: true }).last().click();
  await page
    .getByLabel('Link Google Drive')
    .fill('https://drive.google.com/drive/folders/folder123');
  await page.getByRole('button', { name: 'Kết nối Google & mở ảnh', exact: true }).click();
  await expect(page.locator('.modal-busy')).toContainText('Đang kết nối Google');
  expect(requests).toHaveLength(0);
  await page.evaluate(() =>
    (window as unknown as { grantTestDriveConsent: () => void }).grantTestDriveConsent(),
  );
  await expect(page.locator('.photo-card')).toHaveCount(1);
  expect(requests.length).toBeGreaterThanOrEqual(2);
  expect(requests.every((r) => r.authorization === 'Bearer test-drive-token')).toBe(true);
  await expect(page.locator('.gallery-footer')).toContainText('Đã lưu trên thiết bị');
  await page.reload();
  await page.waitForFunction(() => Boolean((window as unknown as { google?: unknown }).google));
  await expect(
    page.getByRole('button', { name: 'Kết nối lại Google Drive', exact: true }),
  ).toBeVisible();
  const beforeReconnect = requests.length;
  await page.getByRole('button', { name: 'Kết nối lại Google Drive', exact: true }).click();
  await page.evaluate(() =>
    (window as unknown as { grantTestDriveConsent: () => void }).grantTestDriveConsent(),
  );
  await expect(
    page.getByRole('button', { name: 'Kết nối lại Google Drive', exact: true }),
  ).toHaveCount(0);
  await expect.poll(() => requests.length).toBeGreaterThan(beforeReconnect);
});

test('sync remains accessible when the mobile header hides its text', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Đồng bộ', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tiếp tục trên mọi thiết bị' })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Đăng nhập Google để đồng bộ', exact: true }),
  ).toBeVisible();
});

test('restore PC choices, select, compare, save, export and reopen', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Bộ ảnh của bạn.' })).toBeVisible();
  const project = updatePhotos(blankProject(), ['one.png'], () => ({
    category_ids: ['album'],
    stars: 4,
    ai_score: 0,
    note: 'Giữ màu tự nhiên',
  }));
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=',
    'base64',
  );
  const { zipSync, strToU8 } = await import('fflate');
  const backup = zipSync({
    'photo_tags.json': strToU8(JSON.stringify(project)),
    'backup.json': strToU8(
      JSON.stringify({ backup_version: 1, includes_images: true, image_count: 2 }),
    ),
    'images/one.png': new Uint8Array(png),
    'images/two.png': new Uint8Array(png),
  });
  await page.locator('input[accept=".zip,.json"]').setInputFiles({
    name: 'backup-pc.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from(backup),
  });
  await expect(page.getByRole('heading', { name: 'Kiểm tra bản khôi phục' })).toBeVisible();
  await page.getByRole('button', { name: 'Khôi phục lựa chọn', exact: true }).click();
  await expect(page.locator('.photo-card')).toHaveCount(2);
  await expect(page.locator('.score-badge').first()).toContainText('0');
  await page.getByRole('button', { name: 'Chọn one.png', exact: true }).click();
  await page.getByRole('button', { name: 'Chọn two.png', exact: true }).click();
  await page.getByRole('button', { name: 'So sánh', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'So sánh ảnh' })).toBeVisible();
  await expect(page.locator('.viewer-pane')).toHaveCount(2);
  await page.getByRole('button', { name: 'Phóng to', exact: true }).click();
  await expect(page.locator('.viewer-tools')).toContainText('130%');
  await page.getByRole('button', { name: 'Đóng trình xem', exact: true }).click();
  await page.getByRole('button', { name: 'Bỏ chọn ảnh', exact: true }).click();
  await page.getByRole('button', { name: 'Chọn two.png', exact: true }).click();
  if (testInfo.project.name === 'mobile')
    await page.getByRole('button', { name: 'Loại & ghi chú', exact: true }).click();
  await page.locator('.category-choice').filter({ hasText: 'Album' }).click();
  if (testInfo.project.name === 'mobile')
    await page.getByRole('button', { name: 'Đóng bảng chỉnh ảnh', exact: true }).click();
  await expect(page.locator('.package-label')).toContainText('2 khoảnh khắc');
  await page.getByRole('button', { name: 'Hoàn tất & xuất', exact: false }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Chỉ tải JSON', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('photo_tags.json');
  const studioDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Tải gói studio', exact: true }).click();
  await (await studioDownload).saveAs(testInfo.outputPath('studio.zip'));
  await page.getByRole('button', { name: 'Đóng', exact: true }).click();
  await expect(page.locator('.gallery-footer')).toContainText('Đã lưu trên thiết bị');
  await page.reload();
  await expect(page.locator('.photo-card')).toHaveCount(2);
  await expect(page.locator('.package-label')).toContainText('2 khoảnh khắc');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath('gallery.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('blocks a second tab to avoid overwriting local choices', async ({ page, context }) => {
  await page.goto('/');
  await expect(page.locator('.welcome')).toBeVisible();
  const second = await context.newPage();
  await second.goto('/');
  await expect(second.getByRole('alert')).toContainText('đang mở ở một tab khác');
  await page.close();
  await second.getByRole('button', { name: 'Tải lại trang', exact: true }).click();
  await expect(second.locator('.welcome')).toBeVisible();
  await expect(second.getByRole('alert')).toHaveCount(0);
});

test('Google connection config is public client ID only and Drive rejects foreign links', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Cấu hình', exact: true }).click();
  await expect(page.getByLabel('Google OAuth Client ID')).toHaveValue(
    '40087392130-d9qquuudeqt0dfc715u0sg8tllh91lvt.apps.googleusercontent.com',
  );
  await expect(page.locator('textarea').first()).toContainText('');
  await page.getByRole('button', { name: 'Đóng', exact: true }).click();
  await page.getByRole('button', { name: 'Mở link Google Drive', exact: true }).last().click();
  await page.getByLabel('Link Google Drive').fill('https://example.com/folders/12345');
  await page.locator('dialog button[type="submit"]').click();
  await expect(page.getByRole('alert')).toContainText('Chỉ nhận link');
});
