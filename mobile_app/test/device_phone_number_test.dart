import 'package:ai_jurisdiction_mobile/platform/device_phone_number.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel(DevicePhoneNumberService.channelName);
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
  });

  test('returns normalized phone number from native channel', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'getDevicePhoneNumber');
      return ' +421 900 111 222 ';
    });

    const service = DevicePhoneNumberService(
      channel: channel,
      isSupportedOverride: true,
    );

    expect(await service.getDevicePhoneNumber(), '+421900111222');
  });

  test('returns null when native channel returns blank', () async {
    messenger.setMockMethodCallHandler(channel, (call) async => '   ');

    const service = DevicePhoneNumberService(
      channel: channel,
      isSupportedOverride: true,
    );

    expect(await service.getDevicePhoneNumber(), isNull);
  });
}
