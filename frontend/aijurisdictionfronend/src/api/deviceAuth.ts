export const deviceAuthHeaders = (): Record<string, string> => {
  try {
    const raw = window.sessionStorage.getItem("jurisdigta.web.auth.user.v1");
    const user = raw ? JSON.parse(raw) : null;
    return user?.deviceId && user?.deviceAuthToken ? {
      "x-jurisdigta-device-id": String(user.deviceId),
      "x-jurisdigta-device-token": String(user.deviceAuthToken)
    } : {};
  } catch {
    return {};
  }
};
