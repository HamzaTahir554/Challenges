#include<iostream>
using namespace std;
int main()
{
	// How to calculate the (a+b)^2 = a^2 + b^2 + 2ab
	int a,b;
	int c;
	cout<<"Enter A value : ";
	cin>>a;
	cout<<" Enter B value : ";
	cin>>b;
	
	c= (a*a) + (b*b) + 2*a*b;  //(a*a) = a^2 (b*b) = b^2  2*a*b = 2ab
	cout<<"(a+b)^2 = "<<c;
}
