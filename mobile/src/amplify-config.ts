import { Amplify } from 'aws-amplify';

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: 'ap-southeast-2_d0fO5MQej',
      userPoolClientId: 'j31cu1d9h0giauttffmoq8vqm',
      signUpVerificationMethod: 'code',
      loginWith: {
        email: true,
      },
    },
  },
});